import json
import logging
from typing import Dict, TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..tool_calling import run_prebuilt_tool_agent
from .tools import (
    calculate_rush_surcharge,
    compute_compromise,
    compute_unit_economics,
    get_langchain_tools,
    negotiate_price,
    verify_final_margin,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


class FinanceAgentOutput(BaseModel):
    can_proceed: bool | str = False
    discount_rate: float | str = 0.0
    final_price: float | str = 0.0
    total_deal_value: float | str = 0.0
    margin: float | str = 0.0
    reasoning: str = ''
    confidence: float | str = 0.82


class LLMFinanceAgent:
    """LLM agent responsible for price, margin, and final deal economics."""

    def __init__(self, llm: ChatOpenAI, inventory_manager: 'InventoryManager'):
        self.llm = llm
        self.inventory_manager = inventory_manager
        self.name = 'Finance Agent'
        self.prompt = ChatPromptTemplate.from_template(
            """
You are a Finance Agent responsible for final pricing and margin feasibility.

Inputs:
- Quantity: {quantity}
- Requested Price: {requested_price}
- Priority: {priority}
- Material Cost Estimate: {material_cost}
- Shipping Cost Estimate: {shipping_cost}
- Production Overtime Hours: {overtime_hours}

Policy:
- Margin floor: {margin_floor}
- Target margin: {target_margin}
- Rush surcharge rate: {rush_surcharge_rate}

Provide JSON with keys:
can_proceed, discount_rate, final_price, total_deal_value, margin, reasoning, confidence
"""
        )

    def invoke(self, order: dict, procurement_result: Dict, production_result: Dict, logistics_result: Dict) -> Dict:
        quantity = max(1, int(order.get('quantity') or 1))
        requested_price = float(order.get('requested_price') or 10.0)
        material_cost = float(procurement_result.get('total_cost') or 0.0)
        shipping_cost = float(logistics_result.get('shipping_cost') or 0.0)
        overtime_hours = int(production_result.get('overtime_hours') or 0)
        deterministic = self._fallback(order, procurement_result, production_result, logistics_result)

        user_prompt = self.prompt.format(
            quantity=quantity,
            requested_price=requested_price,
            priority=order.get('priority', 'normal'),
            material_cost=material_cost,
            shipping_cost=shipping_cost,
            overtime_hours=overtime_hours,
            margin_floor=self.inventory_manager.finance_policy.get('margin_floor', 0.15),
            target_margin=self.inventory_manager.finance_policy.get('target_margin', 0.22),
            rush_surcharge_rate=self.inventory_manager.finance_policy.get('rush_surcharge_rate', 0.12),
        )

        try:
            agent_run = run_prebuilt_tool_agent(
                llm=self.llm,
                system_prompt=(
                    'You are a Finance Agent. Use finance tools to compute unit economics, rush surcharges, '
                    'price negotiation boundaries, compromise pricing, and final margin viability.'
                ),
                user_prompt=user_prompt,
                tools=get_langchain_tools(
                    self.inventory_manager,
                    order,
                    procurement_result,
                    production_result,
                    logistics_result,
                ),
                response_schema=FinanceAgentOutput,
                agent_name='finance_agent',
            )
            response_text = agent_run['response_text']
            logger.info('[%s] Analysis: %s...', self.name, response_text[:200])

            deterministic = self._fallback(
                order,
                procurement_result,
                production_result,
                logistics_result,
                agent_run.get('tool_results') or {},
            )
            analysis = dict(deterministic)
            analysis.update(agent_run.get('structured_response') or {})
            llm_reasoning = analysis.get('reasoning', response_text)
            return {
                'agent': self.name,
                'can_proceed': bool(deterministic.get('can_proceed', False)),
                'discount_rate': float(deterministic.get('discount_rate', 0.0)),
                'final_price': float(deterministic.get('final_price', requested_price)),
                'total_deal_value': float(deterministic.get('total_deal_value', requested_price * quantity)),
                'margin': float(deterministic.get('margin', 0.22)),
                'reasoning': llm_reasoning if deterministic.get('can_proceed', False) else deterministic.get('reasoning', llm_reasoning),
                'llm_reasoning': llm_reasoning,
                'analysis': response_text,
                'confidence': self._as_float(analysis.get('confidence'), float(deterministic.get('confidence', 0.82))),
                'tool_results': deterministic.get('tool_results', {}),
                'used_tools': agent_run.get('used_tools', []),
                'decision_source': 'deterministic_margin',
            }
        except Exception as exc:
            logger.error('[%s] Error: %s', self.name, str(exc))
            fallback = deterministic
            fallback['reasoning'] = f"Error in analysis: {str(exc)}"
            fallback['analysis'] = str(exc)
            fallback['decision_source'] = 'deterministic_margin'
            return fallback

    def _fallback(
        self,
        order: dict,
        procurement_result: Dict,
        production_result: Dict,
        logistics_result: Dict,
        tool_results: Dict | None = None,
    ) -> Dict:
        policy = self.inventory_manager.finance_policy
        production_policy = self.inventory_manager.production_policy
        tool_results = dict(tool_results or {})
        quantity = max(1, int(order.get('quantity') or 1))
        material_cost_total = float(procurement_result.get('total_cost') or (float(policy.get('base_cost_per_unit', 8.5)) * quantity))
        shipping_total = float(logistics_result.get('shipping_cost') or 0.0)
        overtime_cost_total = float(production_result.get('overtime_hours') or 0) * float(
            production_policy.get('overtime_cost_per_hour', 45.0)
        )
        margin_floor = float(policy.get('margin_floor', 0.15))
        margin = float(policy.get('target_margin', 0.22))
        negotiation_context = order.get('negotiation_context') or {}
        customer_profile = self.inventory_manager.get_customer_profile(order.get('customer', ''))
        if customer_profile.get('tier') == 'strategic' and quantity <= 100:
            margin = margin_floor
        if str(negotiation_context.get('revenue_goal_mode') or '').lower() in {'premium_recovery', 'margin_expansion'}:
            margin = max(margin, float(policy.get('target_margin', 0.22)) + 0.02)

        priority = str(order.get('priority', 'normal')).lower()
        production_strategy = str(negotiation_context.get('production_strategy') or '').lower()
        requested_delivery_days = int(order.get('requested_delivery_days') or 18)
        discount_rate = float(self.inventory_manager.get_volume_discount_rate(quantity))
        unit_economics = tool_results.get('compute_unit_economics')
        if isinstance(unit_economics, list):
            unit_economics = unit_economics[-1] if unit_economics else None
        if not unit_economics:
            unit_economics = compute_unit_economics(
                self.inventory_manager,
                quantity,
                material_cost_total,
                shipping_total,
                overtime_cost_total,
            )
            tool_results['compute_unit_economics'] = unit_economics

        rush = tool_results.get('calculate_rush_surcharge')
        if isinstance(rush, list):
            rush = rush[-1] if rush else None
        if not rush:
            rush = calculate_rush_surcharge(
                self.inventory_manager,
                float(unit_economics.get('unit_cost') or 0.0),
                priority,
                requested_delivery_days,
                production_strategy,
            )
            tool_results['calculate_rush_surcharge'] = rush
        unit_cost = float(rush.get('adjusted_unit_cost') or unit_economics.get('unit_cost') or 0.0)
        minimum_viable_price = round((unit_cost * (1 + margin)) * (1 - discount_rate), 2)
        requested_price = float(order.get('requested_price') or 10.0)
        negotiation = tool_results.get('negotiate_price')
        if isinstance(negotiation, list):
            negotiation = negotiation[-1] if negotiation else None
        if not negotiation:
            negotiation = negotiate_price(self.inventory_manager, customer_profile, requested_price, minimum_viable_price)
            tool_results['negotiate_price'] = negotiation

        compromise = tool_results.get('compute_compromise')
        if isinstance(compromise, list):
            compromise = compromise[-1] if compromise else None
        if not compromise:
            compromise = compute_compromise(
                requested_price,
                minimum_viable_price,
                float(negotiation.get('customer_price_ceiling') or requested_price),
            )
            tool_results['compute_compromise'] = compromise
        final_price = round(max(requested_price, compromise.get('compromise_price', minimum_viable_price)), 2)
        margin_check = tool_results.get('verify_final_margin')
        if isinstance(margin_check, list):
            margin_check = margin_check[-1] if margin_check else None
        if not margin_check:
            margin_check = verify_final_margin(self.inventory_manager, final_price, unit_cost)
            tool_results['verify_final_margin'] = margin_check
        total_deal_value = round(final_price * quantity, 2)
        can_proceed = bool(margin_check.get('meets_floor', False))

        return {
            'can_proceed': can_proceed,
            'discount_rate': discount_rate,
            'final_price': final_price,
            'total_deal_value': total_deal_value,
            'margin': float(margin_check.get('margin') or margin),
            'reasoning': (
                f'Minimum viable commercial price is ${minimum_viable_price:.2f}/unit; '
                f'current negotiation target is ${requested_price:.2f}/unit.'
            ),
            'confidence': 0.84 if can_proceed else 0.66,
            'tool_results': tool_results,
        }

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

    def _as_bool(self, value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        raw = str(value).strip().lower()
        return raw in {'1', 'true', 'yes', 'approved', 'ok'}
