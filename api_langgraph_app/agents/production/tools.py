from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


TOOLS = [
    {
        'name': 'check_production_capacity',
        'description': 'Query factory floor for available capacity and throughput',
        'parameters': {'quantity': 'number', 'delivery_days': 'number'},
    },
    {
        'name': 'calculate_overtime',
        'description': 'Compute overtime schedule and cost for production shortfall',
        'parameters': {'shortfall_days': 'number', 'max_ot_per_day': 'number'},
    },
    {
        'name': 'recalculate_schedule',
        'description': 'Re-evaluate production schedule with adjusted delivery window',
        'parameters': {'delivery_days': 'number'},
    },
    {
        'name': 'lock_production_schedule',
        'description': 'Finalize and lock the production schedule',
        'parameters': {'delivery_days': 'number', 'overtime_hours': 'number'},
    },
]


def _get_strategy_profile(inventory_manager: 'InventoryManager', strategy: str) -> Dict:
    profiles = inventory_manager.factory_schedule.get('strategy_profiles') or {}
    return profiles.get(strategy or 'baseline', profiles.get('baseline', {}))


def _supported_lines(inventory_manager: 'InventoryManager', product_sku: str) -> List[Dict]:
    lines = inventory_manager.factory_schedule.get('lines') or []
    return [line for line in lines if product_sku in (line.get('supported_skus') or [])]


def check_production_capacity(
    inventory_manager: 'InventoryManager',
    product_sku: str,
    quantity: int,
    requested_days: int,
    strategy: str = 'baseline',
) -> Dict:
    lines = _supported_lines(inventory_manager, product_sku)
    strategy_profile = _get_strategy_profile(inventory_manager, strategy)
    working_days = int(inventory_manager.production_policy.get('working_days_per_week', 5))
    planning_weeks = int(inventory_manager.production_policy.get('max_planning_weeks', 4))
    capacity_multiplier = float(strategy_profile.get('capacity_multiplier', 1.0))
    changeover_penalty_days = int(strategy_profile.get('changeover_penalty_days', 0))

    line_allocations = []
    effective_weekly_capacity = 0
    for line in lines:
        base_capacity = int(line.get('weekly_capacity') or 0)
        current_load = float(line.get('current_load') or 0.0)
        available_capacity = int(round(base_capacity * max(0.0, 1.0 - current_load) * capacity_multiplier))
        effective_weekly_capacity += available_capacity
        line_allocations.append(
            {
                'line_id': line.get('line_id'),
                'base_capacity': base_capacity,
                'current_load': current_load,
                'available_capacity': available_capacity,
                'changeover_hours': int(line.get('changeover_hours') or 0),
            }
        )

    if not line_allocations:
        effective_weekly_capacity = int(inventory_manager.production_policy.get('weekly_capacity', 4000) * capacity_multiplier)

    estimated_weeks = quantity / max(1, effective_weekly_capacity)
    production_days = max(5, int(math.ceil(estimated_weeks * working_days)) + changeover_penalty_days)
    capacity_ok = quantity <= effective_weekly_capacity * planning_weeks
    schedule_ok = production_days <= requested_days

    return {
        'strategy': strategy or 'baseline',
        'effective_weekly_capacity': max(1, effective_weekly_capacity),
        'production_days': production_days,
        'capacity_ok': capacity_ok,
        'schedule_ok': schedule_ok,
        'line_allocations': line_allocations,
        'changeover_penalty_days': changeover_penalty_days,
        'preempt_lower_priority': bool(strategy_profile.get('preempt_lower_priority', False)),
    }


def calculate_overtime(
    inventory_manager: 'InventoryManager',
    shortfall_days: int,
    strategy: str = 'baseline',
) -> Dict:
    max_ot_per_day = int(inventory_manager.production_policy.get('max_overtime_hours_per_day', 4))
    overtime_cost_per_hour = float(inventory_manager.production_policy.get('overtime_cost_per_hour', 45.0))
    strategy_profile = _get_strategy_profile(inventory_manager, strategy)
    planned_overtime = int(strategy_profile.get('default_overtime_hours', 0))
    recommended_overtime = min(max_ot_per_day + planned_overtime, max_ot_per_day + 2)
    total_hours = max(0, shortfall_days) * recommended_overtime
    return {
        'recommended_hours_per_day': recommended_overtime,
        'total_overtime_hours': total_hours,
        'overtime_cost': round(total_hours * overtime_cost_per_hour, 2),
    }


def recalculate_schedule(
    inventory_manager: 'InventoryManager',
    product_sku: str,
    quantity: int,
    requested_days: int,
    strategy: str = 'baseline',
) -> Dict:
    capacity = check_production_capacity(inventory_manager, product_sku, quantity, requested_days, strategy)
    shortfall_days = max(0, capacity['production_days'] - requested_days)
    overtime = calculate_overtime(inventory_manager, shortfall_days, strategy)
    adjusted_days = max(4, capacity['production_days'] - min(shortfall_days, overtime['recommended_hours_per_day'] // 2))
    return {
        'capacity': capacity,
        'overtime': overtime,
        'adjusted_days': adjusted_days,
        'can_meet_requested_days': adjusted_days <= requested_days and capacity['capacity_ok'],
    }


def lock_production_schedule(
    inventory_manager: 'InventoryManager',
    product_sku: str,
    quantity: int,
    requested_days: int,
    strategy: str = 'baseline',
) -> Dict:
    schedule = recalculate_schedule(inventory_manager, product_sku, quantity, requested_days, strategy)
    return {
        'schedule_id': f"SCH-{product_sku[:4]}-{quantity}",
        'locked_strategy': strategy or 'baseline',
        'locked_days': schedule['adjusted_days'],
        'locked_overtime_hours': schedule['overtime']['recommended_hours_per_day'],
        'line_allocations': schedule['capacity']['line_allocations'],
    }


TOOL_FUNCTIONS = {
    'check_production_capacity': check_production_capacity,
    'calculate_overtime': calculate_overtime,
    'recalculate_schedule': recalculate_schedule,
    'lock_production_schedule': lock_production_schedule,
}


class _StrategyInput(BaseModel):
    strategy: str = Field('baseline', description='Production strategy to evaluate.')


class _OvertimeInput(BaseModel):
    shortfall_days: int = Field(0, ge=0, description='Days of schedule shortfall that require overtime recovery.')
    strategy: str = Field('baseline', description='Production strategy for overtime planning.')


def get_langchain_tools(inventory_manager: 'InventoryManager', order: dict):
    product_sku = order.get('product_sku') or order.get('product') or 'PMP-STD-100'
    quantity = int(order.get('quantity') or 0)
    requested_days = int(order.get('requested_delivery_days') or 18)
    state: Dict[str, Dict] = {}

    def _capacity(strategy: str) -> Dict:
        key = f'capacity:{strategy}'
        if key not in state:
            state[key] = check_production_capacity(
                inventory_manager,
                product_sku,
                quantity,
                requested_days,
                strategy,
            )
        return state[key]

    def _schedule(strategy: str) -> Dict:
        key = f'schedule:{strategy}'
        if key not in state:
            state[key] = recalculate_schedule(
                inventory_manager,
                product_sku,
                quantity,
                requested_days,
                strategy,
            )
        return state[key]

    def check_production_capacity_tool(strategy: str = 'baseline') -> Dict:
        """Evaluate production capacity for the current order using the requested strategy."""
        return _capacity(strategy)

    def calculate_overtime_tool(shortfall_days: int = 0, strategy: str = 'baseline') -> Dict:
        """Calculate overtime required to recover production shortfall."""
        effective_shortfall = shortfall_days
        if effective_shortfall <= 0:
            effective_shortfall = max(0, int(_schedule(strategy).get('adjusted_days', requested_days)) - requested_days)
        return calculate_overtime(inventory_manager, effective_shortfall, strategy)

    def recalculate_schedule_tool(strategy: str = 'baseline') -> Dict:
        """Recalculate production schedule for the current order and strategy."""
        return _schedule(strategy)

    def lock_production_schedule_tool(strategy: str = 'baseline') -> Dict:
        """Lock a production schedule for the current order and strategy."""
        return lock_production_schedule(
            inventory_manager,
            product_sku,
            quantity,
            requested_days,
            strategy,
        )

    return [
        StructuredTool.from_function(
            func=check_production_capacity_tool,
            name='check_production_capacity',
            description='Evaluate factory capacity and planning-window fit for the current order.',
            args_schema=_StrategyInput,
        ),
        StructuredTool.from_function(
            func=calculate_overtime_tool,
            name='calculate_overtime',
            description='Calculate overtime hours and cost to recover any production shortfall.',
            args_schema=_OvertimeInput,
        ),
        StructuredTool.from_function(
            func=recalculate_schedule_tool,
            name='recalculate_schedule',
            description='Recalculate production schedule after choosing a strategy.',
            args_schema=_StrategyInput,
        ),
        StructuredTool.from_function(
            func=lock_production_schedule_tool,
            name='lock_production_schedule',
            description='Lock the current production schedule for the order.',
            args_schema=_StrategyInput,
        ),
    ]
