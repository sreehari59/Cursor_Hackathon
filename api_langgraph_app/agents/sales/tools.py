from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


TOOLS = [
    {
        'name': 'lookup_customer_profile',
        'description': 'Retrieve customer tier, relationship history, and annual volume',
        'parameters': {'customer': 'string'},
    },
    {
        'name': 'assess_deal_sensitivity',
        'description': 'Evaluate customer sensitivity to price changes',
        'parameters': {'customer': 'string', 'proposed_price': 'number'},
    },
    {
        'name': 'calculate_counter_offer',
        'description': 'Compute counter-offer balancing margin and customer retention',
        'parameters': {'proposed_price': 'number', 'original_price': 'number'},
    },
    {
        'name': 'calculate_deal_value',
        'description': 'Compute final deal metrics for customer report',
        'parameters': {'price': 'number', 'quantity': 'number'},
    },
]


def lookup_customer_profile(inventory_manager: 'InventoryManager', customer: str) -> Dict:
    return dict(inventory_manager.get_customer_profile(customer))


def assess_deal_sensitivity(
    customer_profile: Dict,
    original_price: float,
    proposed_price: float,
    original_delivery_days: int,
    proposed_delivery_days: int,
) -> Dict:
    price_uplift = 0.0 if original_price <= 0 else (proposed_price - original_price) / original_price
    delivery_slip = max(0, proposed_delivery_days - original_delivery_days)
    acceptable_uplift = float(customer_profile.get('max_price_uplift', 0.20))
    acceptable_buffer = int(customer_profile.get('acceptable_delivery_buffer_days', 2))
    return {
        'price_uplift': round(price_uplift, 4),
        'delivery_slip_days': delivery_slip,
        'within_price_tolerance': price_uplift <= acceptable_uplift,
        'within_delivery_tolerance': delivery_slip <= acceptable_buffer,
    }


def calculate_counter_offer(original_price: float, proposed_price: float, sensitivity: Dict) -> Dict:
    if sensitivity.get('within_price_tolerance') and sensitivity.get('within_delivery_tolerance'):
        return {'counter_offer': round(proposed_price, 2), 'customer_acceptance_likelihood': 0.9}

    moderated_price = proposed_price
    if not sensitivity.get('within_price_tolerance'):
        moderated_price = original_price * 1.25
    return {
        'counter_offer': round(moderated_price, 2),
        'customer_acceptance_likelihood': 0.65 if sensitivity.get('within_delivery_tolerance') else 0.5,
    }


def calculate_deal_value(price: float, quantity: int) -> Dict:
    return {
        'unit_price': round(price, 2),
        'quantity': int(quantity),
        'deal_value': round(price * max(1, int(quantity)), 2),
    }


TOOL_FUNCTIONS = {
    'lookup_customer_profile': lookup_customer_profile,
    'assess_deal_sensitivity': assess_deal_sensitivity,
    'calculate_counter_offer': calculate_counter_offer,
    'calculate_deal_value': calculate_deal_value,
}


class _NoArgs(BaseModel):
    pass


class _CounterOfferInput(BaseModel):
    proposed_price: float = Field(..., description='The proposed unit price to counter against.')


class _DealValueInput(BaseModel):
    price: float = Field(..., description='The final or proposed unit price to evaluate.')


def get_langchain_tools(
    inventory_manager: 'InventoryManager',
    order: dict,
    proposed_price: float,
    proposed_delivery_days: int,
):
    customer = order.get('customer', '')
    requested_price = float(order.get('requested_price') or 10.0)
    requested_delivery_days = int(order.get('requested_delivery_days') or 18)
    quantity = int(order.get('quantity') or 1)
    state: Dict[str, Dict] = {}

    def _customer_profile() -> Dict:
        if 'customer_profile' not in state:
            state['customer_profile'] = lookup_customer_profile(inventory_manager, customer)
        return state['customer_profile']

    def _sensitivity(current_price: float) -> Dict:
        key = f'sensitivity:{current_price}'
        if key not in state:
            state[key] = assess_deal_sensitivity(
                _customer_profile(),
                requested_price,
                current_price,
                requested_delivery_days,
                proposed_delivery_days,
            )
        return state[key]

    def lookup_customer_profile_tool() -> Dict:
        """Lookup customer profile for the current account."""
        return _customer_profile()

    def assess_deal_sensitivity_tool() -> Dict:
        """Assess deal sensitivity for the current proposed terms."""
        result = _sensitivity(proposed_price)
        state['latest_sensitivity'] = result
        return result

    def calculate_counter_offer_tool(proposed_price: float) -> Dict:
        """Calculate a counter offer for a proposed unit price."""
        sensitivity = _sensitivity(proposed_price)
        result = calculate_counter_offer(requested_price, proposed_price, sensitivity)
        state['latest_counter_offer'] = result
        return result

    def calculate_deal_value_tool(price: float) -> Dict:
        """Calculate deal value for a unit price and the current order quantity."""
        return calculate_deal_value(price, quantity)

    return [
        StructuredTool.from_function(
            func=lookup_customer_profile_tool,
            name='lookup_customer_profile',
            description='Lookup customer tier, relationship data, and tolerance thresholds.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=assess_deal_sensitivity_tool,
            name='assess_deal_sensitivity',
            description='Assess how the customer will react to the current proposed terms.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=calculate_counter_offer_tool,
            name='calculate_counter_offer',
            description='Calculate a customer-facing counter offer for a proposed unit price.',
            args_schema=_CounterOfferInput,
        ),
        StructuredTool.from_function(
            func=calculate_deal_value_tool,
            name='calculate_deal_value',
            description='Calculate the total deal value for a given unit price.',
            args_schema=_DealValueInput,
        ),
    ]
