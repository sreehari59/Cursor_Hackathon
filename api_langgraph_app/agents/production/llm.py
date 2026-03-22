import json
import logging
from typing import Dict, TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..tool_calling import run_prebuilt_tool_agent
from .tools import (
    calculate_overtime,
    check_production_capacity,
    get_langchain_tools,
    lock_production_schedule,
    recalculate_schedule,
)

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


logger = logging.getLogger(__name__)


class ProductionAgentOutput(BaseModel):
    can_proceed: bool | str = False
    production_days: int | str = 0
    overtime_hours: int | str = 0
    reasoning: str = ''
    confidence: float | str = 0.8


class LLMProductionAgent:
    """LLM agent responsible for manufacturing capacity and schedule feasibility."""

    def __init__(self, llm: ChatOpenAI, inventory_manager: 'InventoryManager'):
        self.llm = llm
        self.inventory_manager = inventory_manager
        self.name = 'Production Agent'
        self.prompt = ChatPromptTemplate.from_template(
            """
You are a Production Agent responsible for manufacturing planning and schedule feasibility.

Task: Analyze whether production can meet requested quantity and timeline.

Order Details:
- Product SKU: {product_sku}
- Quantity: {quantity}
- Requested Delivery Days: {requested_delivery_days}
- Priority: {priority}
- Negotiation Context: {negotiation_context}

Operational Baseline:
- Weekly Capacity: {weekly_capacity}
- Standard Lead Time: {standard_lead_time}
- Max Overtime Hours/Day: {max_overtime}
- Working Days/Week: {working_days}

Provide JSON with keys:
can_proceed, production_days, overtime_hours, reasoning, confidence
"""
        )

    def invoke(self, order: dict) -> Dict:
        requested_days = int(order.get('requested_delivery_days') or 18)
        quantity = int(order.get('quantity') or 0)
        policy = self.inventory_manager.production_policy
        negotiation_context = order.get('negotiation_context') or {}
        deterministic = self._fallback(order.get('product_sku'), quantity, requested_days, negotiation_context)
        user_prompt = self.prompt.format(
            product_sku=order.get('product_sku'),
            quantity=quantity,
            requested_delivery_days=requested_days,
            priority=order.get('priority', 'normal'),
            negotiation_context=json.dumps(negotiation_context, indent=2) if negotiation_context else 'None',
            weekly_capacity=policy.get('weekly_capacity', 4000),
            standard_lead_time=policy.get('standard_lead_time_days', 22),
            max_overtime=policy.get('max_overtime_hours_per_day', 4),
            working_days=policy.get('working_days_per_week', 5),
        )

        try:
            agent_run = run_prebuilt_tool_agent(
                llm=self.llm,
                system_prompt=(
                    'You are a Production Agent. Use production planning tools to evaluate capacity, overtime, '
                    'schedule revisions, and locking the best feasible plan.'
                ),
                user_prompt=user_prompt,
                tools=get_langchain_tools(self.inventory_manager, order),
                response_schema=ProductionAgentOutput,
                agent_name='production_agent',
            )
            response_text = agent_run['response_text']
            logger.info('[%s] Analysis: %s...', self.name, response_text[:200])

            deterministic = self._fallback(
                order.get('product_sku'),
                quantity,
                requested_days,
                negotiation_context,
                agent_run.get('tool_results') or {},
            )
            analysis = dict(deterministic)
            analysis.update(agent_run.get('structured_response') or {})
            llm_reasoning = analysis.get('reasoning', response_text)
            return {
                'agent': self.name,
                'can_proceed': bool(deterministic.get('can_proceed', True)),
                'production_days': int(deterministic.get('production_days', requested_days)),
                'overtime_hours': int(deterministic.get('overtime_hours', 0)),
                'reasoning': llm_reasoning if deterministic.get('can_proceed', True) else deterministic.get('reasoning', llm_reasoning),
                'llm_reasoning': llm_reasoning,
                'analysis': response_text,
                'confidence': self._as_float(analysis.get('confidence'), float(deterministic.get('confidence', 0.8))),
                'tool_results': deterministic.get('tool_results', {}),
                'used_tools': agent_run.get('used_tools', []),
                'decision_source': 'deterministic_capacity',
            }
        except Exception as exc:
            logger.error('[%s] Error: %s', self.name, str(exc))
            fallback = deterministic
            fallback['reasoning'] = f"Error in analysis: {str(exc)}"
            fallback['analysis'] = str(exc)
            fallback['decision_source'] = 'deterministic_capacity'
            return fallback

    def _as_float(self, value, default: float) -> float:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value).strip().lower().replace('%', '').replace('$', '').replace(',', '')
        named = {'low': 0.55, 'medium': 0.72, 'high': 0.88}
        if raw in named:
            return named[raw]
        try:
            return float(raw)
        except ValueError:
            return default

    def _fallback(
        self,
        product_sku: str,
        quantity: int,
        requested_days: int,
        negotiation_context: Dict | None = None,
        tool_results: Dict | None = None,
    ) -> Dict:
        negotiation_context = negotiation_context or {}
        tool_results = dict(tool_results or {})
        production_strategy = str(negotiation_context.get('production_strategy') or '').strip().lower()
        planning_weeks = int(self.inventory_manager.production_policy.get('max_planning_weeks', 4))
        effective_sku = product_sku or negotiation_context.get('product_sku') or negotiation_context.get('product', 'PMP-STD-100')

        capacity = tool_results.get('check_production_capacity')
        if isinstance(capacity, list):
            capacity = capacity[-1] if capacity else None
        if not capacity:
            capacity = check_production_capacity(
                self.inventory_manager,
                effective_sku,
                quantity,
                requested_days,
                production_strategy or 'baseline',
            )
            tool_results['check_production_capacity'] = capacity

        schedule = tool_results.get('recalculate_schedule')
        if isinstance(schedule, list):
            schedule = schedule[-1] if schedule else None
        if not schedule:
            schedule = recalculate_schedule(
                self.inventory_manager,
                effective_sku,
                quantity,
                requested_days,
                production_strategy or 'baseline',
            )
            tool_results['recalculate_schedule'] = schedule

        overtime = tool_results.get('calculate_overtime')
        if isinstance(overtime, list):
            overtime = overtime[-1] if overtime else None
        if not overtime:
            overtime = calculate_overtime(
                self.inventory_manager,
                max(0, schedule.get('adjusted_days', requested_days) - requested_days),
                production_strategy or 'baseline',
            )
            tool_results['calculate_overtime'] = overtime

        lock = tool_results.get('lock_production_schedule')
        if isinstance(lock, list):
            lock = lock[-1] if lock else None
        if not lock:
            lock = lock_production_schedule(
                self.inventory_manager,
                effective_sku,
                quantity,
                max(requested_days, schedule.get('adjusted_days', requested_days)),
                production_strategy or 'baseline',
            )
            tool_results['lock_production_schedule'] = lock
        production_days = int(schedule.get('adjusted_days') or capacity.get('production_days') or requested_days)
        overtime_hours = int(overtime.get('recommended_hours_per_day') or 0)
        capacity_ok = bool(capacity.get('capacity_ok'))
        schedule_ok = bool(schedule.get('can_meet_requested_days'))
        can_proceed = capacity_ok and schedule_ok
        tool_results['lock_production_schedule'] = lock if can_proceed else None

        if can_proceed:
            reasoning = (
                f'Production can schedule {quantity} units in {production_days} days'
                f' using strategy "{production_strategy or "baseline"}".'
            )
            confidence = 0.84
        elif not capacity_ok:
            reasoning = (
                f'Production load exceeds the {planning_weeks}-week planning window even after '
                f'"{production_strategy or "baseline"}" adjustments.'
            )
            confidence = 0.58
        else:
            reasoning = (
                f'Production needs {production_days} days under strategy "{production_strategy or "baseline"}", '
                f'which misses the requested {requested_days}-day timeline.'
            )
            confidence = 0.64

        return {
            'can_proceed': can_proceed,
            'production_days': production_days,
            'overtime_hours': overtime_hours,
            'reasoning': reasoning,
            'confidence': confidence,
            'tool_results': tool_results,
        }
