import json
import logging
from datetime import datetime, timedelta
from typing import Dict, TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..tool_calling import run_prebuilt_tool_agent
from .tools import book_carrier, evaluate_shipping_modes, get_langchain_tools


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


class LogisticsAgentOutput(BaseModel):
    can_proceed: bool | str = True
    location_type: str = 'unknown'
    shipping_mode: str = 'ground'
    shipping_cost: float | str = 0.0
    delivery_date: str = ''
    reasoning: str = ''
    confidence: float | str = 0.8


class LLMLogisticsAgent:
    """LLM agent responsible for shipping cost and ETA analysis."""

    def __init__(self, llm: ChatOpenAI, inventory_manager: 'InventoryManager'):
        self.llm = llm
        self.inventory_manager = inventory_manager
        self.name = 'Logistics Agent'
        self.prompt = ChatPromptTemplate.from_template(
            """
You are a Logistics Agent responsible for calculating shipping costs and delivery timelines.

Task: Analyze the following order request and provide:
1. Location type classification (local/regional/national/international)
2. Estimated shipping cost
3. Estimated delivery date
4. Any logistical concerns
5. Your confidence level (0.0-1.0)

Order Details:
- Product SKU: {product_sku}
- Quantity: {quantity}
- Customer Location: {customer_location}
- Priority: {priority}
- Material Cost: {material_cost}
- Planned Production Days: {production_days}

Provide your analysis in JSON format with keys: can_proceed, location_type, shipping_mode, shipping_cost, delivery_date, reasoning, confidence
"""
        )

    def invoke(self, order: dict, material_cost: float, production_days: int) -> Dict:
        logger.info('[%s] Calculating logistics for %s', self.name, order['customer_location'])

        user_prompt = self.prompt.format(
            product_sku=order['product_sku'],
            quantity=order['quantity'],
            customer_location=order['customer_location'],
            priority=order.get('priority', 'normal'),
            material_cost=material_cost,
            production_days=production_days,
        )

        try:
            agent_run = run_prebuilt_tool_agent(
                llm=self.llm,
                system_prompt=(
                    'You are a Logistics Agent. Use logistics tools to compare shipping modes, '
                    'check route clearance, and book the best feasible carrier.'
                ),
                user_prompt=user_prompt,
                tools=get_langchain_tools(self.inventory_manager, order, production_days),
                response_schema=LogisticsAgentOutput,
                agent_name='logistics_agent',
            )
            response_text = agent_run['response_text']
            logger.info('[%s] Analysis: %s...', self.name, response_text[:200])

            fallback = self._fallback(order, production_days, agent_run.get('tool_results') or {})
            analysis = dict(fallback)
            analysis.update(agent_run.get('structured_response') or {})
            delivery_date = self._sanitize_delivery_date(
                analysis.get('delivery_date'),
                order.get('priority'),
                production_days,
            )
            return {
                'agent': self.name,
                'can_proceed': bool(fallback.get('can_proceed', True)),
                'location_type': analysis.get('location_type', fallback.get('location_type', 'unknown')),
                'shipping_mode': analysis.get(
                    'shipping_mode',
                    fallback.get('shipping_mode', self.inventory_manager.logistics_policy.get('default_mode', 'ground')),
                ),
                'shipping_cost': float(fallback.get('shipping_cost', analysis.get('shipping_cost', 50))),
                'delivery_date': fallback.get('delivery_date', delivery_date),
                'reasoning': analysis.get('reasoning', response_text) if fallback.get('can_proceed', True) else fallback.get('reasoning', response_text),
                'llm_reasoning': analysis.get('reasoning', response_text),
                'analysis': response_text,
                'confidence': self._as_float(analysis.get('confidence'), float(fallback.get('confidence', 0.8))),
                'tool_results': fallback.get('tool_results', {}),
                'used_tools': agent_run.get('used_tools', []),
                'decision_source': 'deterministic_logistics',
            }
        except Exception as exc:
            logger.error('[%s] Error: %s', self.name, str(exc))
            fallback = self._fallback(order, production_days)
            return {
                'agent': self.name,
                'can_proceed': bool(fallback.get('can_proceed', True)),
                'location_type': fallback.get('location_type', 'unknown'),
                'shipping_mode': fallback.get('shipping_mode', 'ground'),
                'shipping_cost': float(fallback.get('shipping_cost', 50.0)),
                'delivery_date': fallback.get('delivery_date', self._default_delivery_date(order.get('priority'), production_days)),
                'reasoning': f'Error in analysis: {str(exc)}',
                'analysis': str(exc),
                'confidence': float(fallback.get('confidence', 0.5)),
                'tool_results': fallback.get('tool_results', {}),
                'decision_source': 'deterministic_logistics',
            }

    def _fallback(self, order: dict, production_days: int, tool_results: Dict | None = None) -> Dict:
        requested_days = int(order.get('requested_delivery_days') or 18)
        location_profile = self.inventory_manager.get_location_profile(order.get('customer_location'))
        location_type = location_profile.get('type', 'national')
        tool_results = dict(tool_results or {})

        mode_result = tool_results.get('evaluate_shipping_modes')
        if isinstance(mode_result, list):
            mode_result = mode_result[-1] if mode_result else None
        if not mode_result:
            mode_result = evaluate_shipping_modes(self.inventory_manager, order, production_days)
            tool_results['evaluate_shipping_modes'] = mode_result

        recommended = mode_result.get('recommended') or {}
        mode = recommended.get('mode', self.inventory_manager.logistics_policy.get('default_mode', 'ground'))
        booking = tool_results.get('book_carrier')
        if isinstance(booking, list):
            booking = next((item for item in booking if item.get('mode') == mode), booking[-1] if booking else None)
        if not booking:
            booking = book_carrier(self.inventory_manager, mode_result, order, production_days)
            tool_results['book_carrier'] = booking

        total_days = int(recommended.get('total_days') or (production_days + 5))
        shipping_cost = float(booking.get('shipping_cost') or recommended.get('shipping_cost') or 0.0)
        delivery_date = booking.get('delivery_date') or (datetime.utcnow().date() + timedelta(days=total_days)).strftime('%Y-%m-%d')
        can_proceed = bool(recommended.get('meets_schedule', total_days <= requested_days))

        return {
            'can_proceed': can_proceed,
            'location_type': location_type,
            'shipping_mode': mode,
            'shipping_cost': shipping_cost,
            'delivery_date': delivery_date,
            'reasoning': (
                f'Fallback logistics selected {mode} for {location_type} delivery. '
                f'Total lead time is {total_days} days.'
            ),
            'confidence': 0.8 if can_proceed else 0.62,
            'tool_results': tool_results,
        }

    def _default_delivery_date(self, priority: str = 'normal', production_days: int = 10) -> str:
        days = production_days + (2 if priority == 'expedited' else 5)
        return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

    def _sanitize_delivery_date(self, raw_date, priority: str, production_days: int) -> str:
        if isinstance(raw_date, str):
            try:
                parsed = datetime.strptime(raw_date, '%Y-%m-%d').date()
                if parsed >= datetime.utcnow().date():
                    return raw_date
            except ValueError:
                pass
        return self._default_delivery_date(priority, production_days)

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
