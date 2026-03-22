from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


TOOLS = [
    {
        'name': 'build_material_requirements',
        'description': 'Build SKU BOM requirements and identify current material shortfalls',
        'parameters': {},
    },
    {
        'name': 'query_supplier_inventory',
        'description': 'Check supplier for material availability and lead time',
        'parameters': {'supplier_name': 'string'},
    },
    {
        'name': 'query_alternate_supplier',
        'description': 'Check alternate supplier as backup option',
        'parameters': {},
    },
    {
        'name': 'reserve_materials',
        'description': 'Reserve raw materials with selected supplier',
        'parameters': {'supplier_name': 'string'},
    },
    {
        'name': 'submit_purchase_order',
        'description': 'Submit final purchase order to supplier',
        'parameters': {'supplier_name': 'string'},
    },
]


def build_material_requirements(order: dict, inventory_manager: 'InventoryManager') -> Dict:
    sku = order.get('product_sku')
    quantity = max(0, int(order.get('quantity') or 0))
    bom = inventory_manager.get_product_bom(sku)
    if not bom:
        return {'sku': sku, 'quantity': quantity, 'materials': {}, 'feasible_quantity': 0}

    materials = {}
    feasible_quantity = None
    for material_id, qty_per_unit in bom.get('materials', {}).items():
        required = int(qty_per_unit * quantity)
        available = int(inventory_manager.get_material_stock(material_id) or 0)
        unit_cost = float(inventory_manager.get_material_price(material_id) or 0.0)
        immediate_units = available // max(1, int(qty_per_unit))
        feasible_quantity = immediate_units if feasible_quantity is None else min(feasible_quantity, immediate_units)
        materials[material_id] = {
            'quantity_per_unit': int(qty_per_unit),
            'required': required,
            'available': available,
            'shortfall': max(0, required - available),
            'is_available': available >= required,
            'unit_cost': unit_cost,
            'line_cost': round(required * unit_cost, 2),
        }

    return {
        'sku': sku,
        'quantity': quantity,
        'materials': materials,
        'feasible_quantity': max(0, feasible_quantity or 0),
    }


def query_supplier_inventory(
    inventory_manager: 'InventoryManager',
    shortages: Dict[str, Dict],
    supplier_name: str,
) -> Dict:
    supplier = (inventory_manager.supplier_catalog.get('suppliers') or {}).get(supplier_name, {})
    supplier_materials = supplier.get('materials', {})
    coverage = {}
    can_fulfill = True

    for material_id, shortage in shortages.items():
        shortfall = int(shortage.get('shortfall') or 0)
        supplier_item = supplier_materials.get(material_id, {})
        supplier_available = int(supplier_item.get('available') or 0)
        reserved = min(shortfall, supplier_available)
        if reserved < shortfall:
            can_fulfill = False
        coverage[material_id] = {
            'shortfall': shortfall,
            'supplier_available': supplier_available,
            'reserved_quantity': reserved,
            'price_multiplier': float(supplier_item.get('price_multiplier', 1.0)),
        }

    return {
        'supplier': supplier_name,
        'lead_time_days': int(supplier.get('lead_time_days') or 0),
        'reservation_window_days': int(supplier.get('reservation_window_days') or 0),
        'coverage': coverage,
        'can_fulfill': can_fulfill,
    }


def query_alternate_supplier(inventory_manager: 'InventoryManager', shortages: Dict[str, Dict]) -> Dict:
    supplier_name = inventory_manager.procurement_policy.get('alternate_supplier', 'Alternate Supplier')
    return query_supplier_inventory(inventory_manager, shortages, supplier_name)


def reserve_materials(
    inventory_manager: 'InventoryManager',
    supplier_result: Dict,
) -> Dict:
    coverage = supplier_result.get('coverage') or {}
    reserved_materials = {
        material_id: {
            'reserved_quantity': int(item.get('reserved_quantity') or 0),
            'price_multiplier': float(item.get('price_multiplier') or 1.0),
        }
        for material_id, item in coverage.items()
        if int(item.get('reserved_quantity') or 0) > 0
    }
    return {
        'supplier': supplier_result.get('supplier'),
        'reservation_id': f"RES-{str(supplier_result.get('supplier', 'SUP')).replace(' ', '-')[:8].upper()}",
        'reserved_materials': reserved_materials,
        'lead_time_days': int(supplier_result.get('lead_time_days') or 0),
    }


def submit_purchase_order(
    inventory_manager: 'InventoryManager',
    supplier_name: str,
    reserved_materials: Dict[str, Dict],
) -> Dict:
    total_cost = 0.0
    line_items = []
    for material_id, item in reserved_materials.items():
        quantity = int(item.get('reserved_quantity') or 0)
        unit_cost = float(inventory_manager.get_material_price(material_id) or 0.0)
        multiplier = float(item.get('price_multiplier') or 1.0)
        effective_unit_cost = round(unit_cost * multiplier, 2)
        line_cost = round(effective_unit_cost * quantity, 2)
        total_cost += line_cost
        line_items.append(
            {
                'material_id': material_id,
                'quantity': quantity,
                'effective_unit_cost': effective_unit_cost,
                'line_cost': line_cost,
            }
        )

    return {
        'supplier': supplier_name,
        'purchase_order_id': f"PO-{str(supplier_name).replace(' ', '-')[:8].upper()}",
        'line_items': line_items,
        'total_cost': round(total_cost, 2),
    }


TOOL_FUNCTIONS = {
    'build_material_requirements': build_material_requirements,
    'query_supplier_inventory': query_supplier_inventory,
    'query_alternate_supplier': query_alternate_supplier,
    'reserve_materials': reserve_materials,
    'submit_purchase_order': submit_purchase_order,
}


class _NoArgs(BaseModel):
    pass


class _SupplierNameInput(BaseModel):
    supplier_name: str = Field(..., description='Supplier to query for procurement coverage.')


def get_langchain_tools(inventory_manager: 'InventoryManager', order: dict):
    state: Dict[str, Dict] = {}

    def _requirements() -> Dict:
        if 'requirements' not in state:
            state['requirements'] = build_material_requirements(order, inventory_manager)
        return state['requirements']

    def _shortages() -> Dict[str, Dict]:
        requirements = _requirements()
        return {
            material_id: info
            for material_id, info in (requirements.get('materials') or {}).items()
            if int(info.get('shortfall') or 0) > 0
        }

    def build_material_requirements_tool() -> Dict:
        """Build BOM material requirements for the current order."""
        return _requirements()

    def query_supplier_inventory_tool(supplier_name: str) -> Dict:
        """Check whether a named supplier can fill current procurement shortages."""
        return query_supplier_inventory(inventory_manager, _shortages(), supplier_name)

    def query_alternate_supplier_tool() -> Dict:
        """Check the configured alternate supplier against current procurement shortages."""
        return query_alternate_supplier(inventory_manager, _shortages())

    def reserve_materials_tool(supplier_name: str) -> Dict:
        """Reserve current procurement shortages with the named supplier."""
        supplier_result = query_supplier_inventory(inventory_manager, _shortages(), supplier_name)
        state[f'reservation:{supplier_name}'] = reserve_materials(inventory_manager, supplier_result)
        return state[f'reservation:{supplier_name}']

    def submit_purchase_order_tool(supplier_name: str) -> Dict:
        """Submit a purchase order using the current reservation for the named supplier."""
        reservation_key = f'reservation:{supplier_name}'
        reservation = state.get(reservation_key)
        if reservation is None:
            supplier_result = query_supplier_inventory(inventory_manager, _shortages(), supplier_name)
            reservation = reserve_materials(inventory_manager, supplier_result)
            state[reservation_key] = reservation
        return submit_purchase_order(
            inventory_manager,
            supplier_name,
            reservation.get('reserved_materials', {}),
        )

    return [
        StructuredTool.from_function(
            func=build_material_requirements_tool,
            name='build_material_requirements',
            description='Build BOM requirements and identify current material shortfalls for the order.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=query_supplier_inventory_tool,
            name='query_supplier_inventory',
            description='Check a named supplier for material coverage and lead time.',
            args_schema=_SupplierNameInput,
        ),
        StructuredTool.from_function(
            func=query_alternate_supplier_tool,
            name='query_alternate_supplier',
            description='Check the configured alternate supplier for material coverage and lead time.',
            args_schema=_NoArgs,
        ),
        StructuredTool.from_function(
            func=reserve_materials_tool,
            name='reserve_materials',
            description='Reserve current shortages with a named supplier.',
            args_schema=_SupplierNameInput,
        ),
        StructuredTool.from_function(
            func=submit_purchase_order_tool,
            name='submit_purchase_order',
            description='Create a purchase order for reserved shortages with a named supplier.',
            args_schema=_SupplierNameInput,
        ),
    ]
