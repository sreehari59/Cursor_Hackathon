from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


TOOLS = [
    {
        'name': 'evaluate_shipping_modes',
        'description': 'Compare ground, express, and air freight for delivery window',
        'parameters': {'delivery_days': 'number'},
    },
    {
        'name': 'check_route_clearance',
        'description': 'Verify carrier availability and route clearance',
        'parameters': {'origin': 'string', 'destination': 'string', 'quantity': 'number'},
    },
    {
        'name': 're_evaluate_mode',
        'description': 'Re-check shipping mode after delivery adjustment',
        'parameters': {'delivery_days': 'number'},
    },
    {
        'name': 'book_carrier',
        'description': 'Book carrier and lock route for final delivery',
        'parameters': {'mode': 'string', 'delivery_days': 'number'},
    },
]


def check_route_clearance(
    inventory_manager: 'InventoryManager',
    destination: str,
    quantity: int,
    mode: str,
) -> Dict:
    location_type = inventory_manager.get_location_profile(destination).get('type', 'national')
    carriers = (inventory_manager.carrier_network.get('carrier_networks') or {}).get(mode, [])
    viable = []
    for carrier in carriers:
        supported_locations = carrier.get('supported_locations') or []
        if location_type not in supported_locations:
            continue
        if quantity > int(carrier.get('max_units') or 0):
            continue
        viable.append(
            {
                'name': carrier.get('name'),
                'fixed_fee': float(carrier.get('fixed_fee') or 0.0),
                'reliability': float(carrier.get('reliability') or 0.9),
            }
        )

    viable.sort(key=lambda item: (-item['reliability'], item['fixed_fee']))
    return {
        'location_type': location_type,
        'mode': mode,
        'available': bool(viable),
        'carriers': viable,
    }


def evaluate_shipping_modes(
    inventory_manager: 'InventoryManager',
    order: dict,
    production_days: int,
) -> Dict:
    quantity = max(1, int(order.get('quantity') or 1))
    requested_days = int(order.get('requested_delivery_days') or 18)
    destination = order.get('customer_location', 'national')
    modes = inventory_manager.logistics_policy.get('shipping_modes', {})
    evaluations: List[Dict] = []

    for mode, cfg in modes.items():
        clearance = check_route_clearance(inventory_manager, destination, quantity, mode)
        if not clearance['available']:
            continue
        transit_days = int(cfg.get('transit_days', 5))
        total_days = production_days + transit_days
        shipping_cost = round((float(cfg.get('cost_per_unit', 0.3)) * quantity) + clearance['carriers'][0]['fixed_fee'], 2)
        evaluations.append(
            {
                'mode': mode,
                'transit_days': transit_days,
                'total_days': total_days,
                'shipping_cost': shipping_cost,
                'meets_schedule': total_days <= requested_days,
                'carrier': clearance['carriers'][0]['name'],
                'location_type': clearance['location_type'],
                'reliability': clearance['carriers'][0]['reliability'],
            }
        )

    evaluations.sort(key=lambda item: (not item['meets_schedule'], item['shipping_cost'], -item['reliability']))
    recommended = evaluations[0] if evaluations else None
    return {
        'evaluations': evaluations,
        'recommended': recommended,
    }


def re_evaluate_mode(
    inventory_manager: 'InventoryManager',
    order: dict,
    production_days: int,
) -> Dict:
    return evaluate_shipping_modes(inventory_manager, order, production_days)


def book_carrier(
    inventory_manager: 'InventoryManager',
    mode_result: Dict,
    order: dict,
    production_days: int,
) -> Dict:
    recommended = mode_result.get('recommended') or {}
    total_days = int(recommended.get('total_days') or (production_days + 5))
    return {
        'booking_id': f"BOOK-{recommended.get('carrier', 'CARRIER')[:6].upper()}",
        'carrier': recommended.get('carrier'),
        'mode': recommended.get('mode'),
        'delivery_date': (datetime.utcnow().date() + timedelta(days=total_days)).strftime('%Y-%m-%d'),
        'shipping_cost': float(recommended.get('shipping_cost') or 0.0),
    }


TOOL_FUNCTIONS = {
    'evaluate_shipping_modes': evaluate_shipping_modes,
    'check_route_clearance': check_route_clearance,
    're_evaluate_mode': re_evaluate_mode,
    'book_carrier': book_carrier,
}


class _NoArgs(BaseModel):
    pass


class _ModeInput(BaseModel):
    mode: str = Field(..., description='Shipping mode to inspect or book.')


def get_langchain_tools(inventory_manager: 'InventoryManager', order: dict, production_days: int):
    state: Dict[str, Dict] = {}

    def _mode_result() -> Dict:
        if 'mode_result' not in state:
            state['mode_result'] = evaluate_shipping_modes(inventory_manager, order, production_days)
        return state['mode_result']

    def evaluate_shipping_modes_tool() -> Dict:
        """Compare available shipping modes for the current order."""
        return _mode_result()

    def check_route_clearance_tool(mode: str) -> Dict:
        """Check carrier and route clearance for a specific shipping mode."""
        return check_route_clearance(
            inventory_manager,
            order.get('customer_location', 'national'),
            int(order.get('quantity') or 1),
            mode,
        )

    def re_evaluate_mode_tool() -> Dict:
        """Re-evaluate shipping modes for the current order after a schedule revision."""
        refreshed = re_evaluate_mode(inventory_manager, order, production_days)
        state['mode_result'] = refreshed
        return refreshed

    def book_carrier_tool(mode: str) -> Dict:
        """Book a carrier for a specific shipping mode."""
        mode_result = _mode_result()
        recommended = mode_result.get('recommended') or {}
        if recommended.get('mode') != mode:
            evaluations = mode_result.get('evaluations') or []
            selected = next((item for item in evaluations if item.get('mode') == mode), None)
            mode_result = {'evaluations': evaluations, 'recommended': selected or recommended}
        return book_carrier(inventory_manager, mode_result, order, production_days)

    return [
        StructuredTool.from_function(
            func=evaluate_shipping_modes_tool,
            name='evaluate_shipping_modes',
            description='Compare available shipping modes for the current order.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=check_route_clearance_tool,
            name='check_route_clearance',
            description='Check carrier availability and route clearance for a specific mode.',
            args_schema=_ModeInput,
        ),
        StructuredTool.from_function(
            func=re_evaluate_mode_tool,
            name='re_evaluate_mode',
            description='Re-evaluate shipping modes after schedule changes.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=book_carrier_tool,
            name='book_carrier',
            description='Book a carrier for the chosen shipping mode.',
            args_schema=_ModeInput,
        ),
    ]
