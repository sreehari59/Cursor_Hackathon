from __future__ import annotations

from typing import Optional, TYPE_CHECKING, Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


TOOLS = [
    {
        'name': 'compute_unit_economics',
        'description': 'Run margin analysis at a given price point',
        'parameters': {'price': 'number', 'overtime_hours': 'number'},
    },
    {
        'name': 'calculate_rush_surcharge',
        'description': 'Calculate rush surcharge to meet margin floor',
        'parameters': {'base_price': 'number', 'surcharge_rate': 'number'},
    },
    {
        'name': 'negotiate_price',
        'description': 'Open price negotiation with initial position',
        'parameters': {'initial_price': 'number'},
    },
    {
        'name': 'compute_compromise',
        'description': 'Test a compromise price point against margin thresholds',
        'parameters': {'offer_price': 'number'},
    },
    {
        'name': 'verify_final_margin',
        'description': 'Final margin verification at locked price',
        'parameters': {'final_price': 'number'},
    },
]


def compute_unit_economics(
    inventory_manager: 'InventoryManager',
    quantity: int,
    material_cost_total: float,
    shipping_total: float,
    overtime_cost_total: float,
) -> Dict:
    finance_policy = inventory_manager.finance_policy
    base_cost_per_unit = float(finance_policy.get('base_cost_per_unit', 8.5))
    material_unit_cost = material_cost_total / max(1, quantity)
    if quantity <= 100:
        material_cap_multiplier = 1.08
    elif quantity <= 1000:
        material_cap_multiplier = 1.18
    else:
        material_cap_multiplier = 1.30
    normalized_material_unit_cost = min(
        max(base_cost_per_unit, material_unit_cost),
        base_cost_per_unit * material_cap_multiplier,
    )
    unit_cost = normalized_material_unit_cost + (shipping_total / max(1, quantity)) + (overtime_cost_total / max(1, quantity))
    return {
        'base_cost_per_unit': base_cost_per_unit,
        'normalized_material_unit_cost': round(normalized_material_unit_cost, 2),
        'unit_cost': round(unit_cost, 2),
    }


def calculate_rush_surcharge(
    inventory_manager: 'InventoryManager',
    unit_cost: float,
    priority: str,
    requested_delivery_days: int,
    production_strategy: str = '',
) -> Dict:
    rush_rate = float(inventory_manager.finance_policy.get('rush_surcharge_rate', 0.12))
    apply_surcharge = str(priority or '').lower() in {'rush', 'expedited', 'critical'} and (
        requested_delivery_days <= 14 or production_strategy in {'preempt_and_overtime', 'phased_split_delivery'}
    )
    surcharge_amount = round(unit_cost * rush_rate, 2) if apply_surcharge else 0.0
    return {
        'applied': apply_surcharge,
        'surcharge_rate': rush_rate if apply_surcharge else 0.0,
        'surcharge_amount': surcharge_amount,
        'adjusted_unit_cost': round(unit_cost + surcharge_amount, 2),
    }


def negotiate_price(
    inventory_manager: 'InventoryManager',
    customer_profile: Dict,
    requested_price: float,
    minimum_viable_price: float,
) -> Dict:
    price_ceiling = round(requested_price * (1 + float(customer_profile.get('max_price_uplift', 0.20))), 2)
    return {
        'requested_price': requested_price,
        'minimum_viable_price': minimum_viable_price,
        'customer_price_ceiling': price_ceiling,
        'within_customer_tolerance': minimum_viable_price <= price_ceiling,
    }


def compute_compromise(requested_price: float, minimum_viable_price: float, customer_price_ceiling: float) -> Dict:
    compromise_price = min(customer_price_ceiling, max(requested_price, minimum_viable_price))
    return {
        'compromise_price': round(compromise_price, 2),
        'fully_recovers_margin': compromise_price >= minimum_viable_price,
    }


def verify_final_margin(
    inventory_manager: 'InventoryManager',
    final_price: float,
    unit_cost: float,
) -> Dict:
    margin = 0.0 if final_price <= 0 else (final_price - unit_cost) / final_price
    margin_floor = float(inventory_manager.finance_policy.get('margin_floor', 0.15))
    return {
        'margin': round(margin, 4),
        'margin_floor': margin_floor,
        'meets_floor': margin >= margin_floor,
    }


TOOL_FUNCTIONS = {
    'compute_unit_economics': compute_unit_economics,
    'calculate_rush_surcharge': calculate_rush_surcharge,
    'negotiate_price': negotiate_price,
    'compute_compromise': compute_compromise,
    'verify_final_margin': verify_final_margin,
}


class _NoArgs(BaseModel):
    pass


class _CompromiseInput(BaseModel):
    customer_price_ceiling: Optional[float] = Field(
        None,
        description='Optional customer ceiling to test. Leave empty to use policy-derived value.',
    )


class _FinalMarginInput(BaseModel):
    final_price: Optional[float] = Field(
        None,
        description='Optional final price to verify. Leave empty to use the current compromise price.',
    )


def get_langchain_tools(
    inventory_manager: 'InventoryManager',
    order: dict,
    procurement_result: Dict,
    production_result: Dict,
    logistics_result: Dict,
):
    quantity = max(1, int(order.get('quantity') or 1))
    policy = inventory_manager.finance_policy
    production_policy = inventory_manager.production_policy
    requested_price = float(order.get('requested_price') or 10.0)
    material_cost_total = float(procurement_result.get('total_cost') or (float(policy.get('base_cost_per_unit', 8.5)) * quantity))
    shipping_total = float(logistics_result.get('shipping_cost') or 0.0)
    overtime_cost_total = float(production_result.get('overtime_hours') or 0) * float(
        production_policy.get('overtime_cost_per_hour', 45.0)
    )
    negotiation_context = order.get('negotiation_context') or {}
    customer_profile = inventory_manager.get_customer_profile(order.get('customer', ''))
    state: Dict[str, Dict] = {'customer_profile': customer_profile}

    def _unit_economics() -> Dict:
        if 'unit_economics' not in state:
            state['unit_economics'] = compute_unit_economics(
                inventory_manager,
                quantity,
                material_cost_total,
                shipping_total,
                overtime_cost_total,
            )
        return state['unit_economics']

    def _rush() -> Dict:
        if 'rush' not in state:
            state['rush'] = calculate_rush_surcharge(
                inventory_manager,
                float(_unit_economics().get('unit_cost') or 0.0),
                str(order.get('priority', 'normal')).lower(),
                int(order.get('requested_delivery_days') or 18),
                str(negotiation_context.get('production_strategy') or '').lower(),
            )
        return state['rush']

    def _minimum_viable_price() -> float:
        margin = float(policy.get('target_margin', 0.22))
        margin_floor = float(policy.get('margin_floor', 0.15))
        if customer_profile.get('tier') == 'strategic' and quantity <= 100:
            margin = margin_floor
        if str(negotiation_context.get('revenue_goal_mode') or '').lower() in {'premium_recovery', 'margin_expansion'}:
            margin = max(margin, float(policy.get('target_margin', 0.22)) + 0.02)
        discount_rate = float(inventory_manager.get_volume_discount_rate(quantity))
        unit_cost = float(_rush().get('adjusted_unit_cost') or _unit_economics().get('unit_cost') or 0.0)
        return round((unit_cost * (1 + margin)) * (1 - discount_rate), 2)

    def compute_unit_economics_tool() -> Dict:
        """Compute normalized unit economics for the current order."""
        return _unit_economics()

    def calculate_rush_surcharge_tool() -> Dict:
        """Calculate rush surcharge impact for the current order."""
        return _rush()

    def negotiate_price_tool() -> Dict:
        """Check whether the minimum viable price fits within customer tolerance."""
        result = negotiate_price(
            inventory_manager,
            customer_profile,
            requested_price,
            _minimum_viable_price(),
        )
        state['negotiation'] = result
        return result

    def compute_compromise_tool(customer_price_ceiling: Optional[float] = None) -> Dict:
        """Compute a compromise price between the customer ask and minimum viable price."""
        negotiation = state.get('negotiation') or negotiate_price_tool()
        ceiling = float(customer_price_ceiling) if customer_price_ceiling is not None else float(
            negotiation.get('customer_price_ceiling') or requested_price
        )
        result = compute_compromise(
            requested_price,
            _minimum_viable_price(),
            ceiling,
        )
        state['compromise'] = result
        return result

    def verify_final_margin_tool(final_price: Optional[float] = None) -> Dict:
        """Verify whether a final price meets the configured margin floor."""
        compromise = state.get('compromise') or compute_compromise_tool()
        effective_price = float(final_price) if final_price is not None else float(
            compromise.get('compromise_price') or requested_price
        )
        return verify_final_margin(
            inventory_manager,
            effective_price,
            float(_rush().get('adjusted_unit_cost') or _unit_economics().get('unit_cost') or 0.0),
        )

    return [
        StructuredTool.from_function(
            func=compute_unit_economics_tool,
            name='compute_unit_economics',
            description='Compute unit economics for the current deal.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=calculate_rush_surcharge_tool,
            name='calculate_rush_surcharge',
            description='Apply rush surcharge logic for the current deal.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=negotiate_price_tool,
            name='negotiate_price',
            description='Compare the customer ask with the minimum viable price.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=compute_compromise_tool,
            name='compute_compromise',
            description='Compute a compromise price for the current deal.',
            args_schema=_CompromiseInput,
        ),
        StructuredTool.from_function(
            func=verify_final_margin_tool,
            name='verify_final_margin',
            description='Verify whether a final price meets the margin floor.',
            args_schema=_FinalMarginInput,
        ),
    ]
