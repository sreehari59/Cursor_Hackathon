import json
import logging
from typing import Dict, TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..tool_calling import run_prebuilt_tool_agent
from .tools import (
    assess_deal_sensitivity,
    calculate_counter_offer,
    calculate_deal_value,
    get_langchain_tools,
    lookup_customer_profile,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


class SalesAgentOutput(BaseModel):
    can_proceed: bool | str = False
    agreed_price: float | str = 0.0
    reasoning: str = ''
    confidence: float | str = 0.82


class LLMSalesAgent:
    """LLM agent responsible for customer acceptability and final commercial sign-off."""

    def __init__(self, llm: ChatOpenAI, inventory_manager: 'InventoryManager'):
        self.llm = llm
        self.inventory_manager = inventory_manager
        self.name = 'Sales Agent'
        self.prompt = ChatPromptTemplate.from_template(
            """
You are a Sales Agent responsible for customer-acceptable terms and relationship management.

Inputs:
- Customer: {customer}
- Customer Tier: {customer_tier}
- Relationship Years: {relationship_years}
- Annual Volume: {annual_volume}
- Requested Price: {requested_price}
- Requested Delivery Days: {requested_days}
- Proposed Price: {proposed_price}
- Proposed Delivery Date: {delivery_date}

Provide JSON with keys:
can_proceed, agreed_price, reasoning, confidence
"""
        )

    def invoke(self, order: dict, finance_result: Dict, logistics_result: Dict) -> Dict:
        negotiation_context = order.get('negotiation_context') or {}
        requested_price = float(order.get('requested_price') or 10.0)
        proposed_price = float(finance_result.get('final_price') or requested_price)
        anchor_requested_price = float(
            negotiation_context.get('original_requested_price')
            or order.get('requested_price')
            or 10.0
        )
        customer_profile = lookup_customer_profile(self.inventory_manager, order.get('customer', ''))
        requested_days = int(order.get('requested_delivery_days') or 18)
        delivery_date = logistics_result.get('delivery_date', '')
        sensitivity = assess_deal_sensitivity(
            customer_profile,
            anchor_requested_price,
            proposed_price,
            requested_days,
            requested_days,
        )
        counter = calculate_counter_offer(anchor_requested_price, proposed_price, sensitivity)
        deal_value = calculate_deal_value(float(counter.get('counter_offer', proposed_price)), int(order.get('quantity') or 1))

        user_prompt = self.prompt.format(
            customer=order.get('customer', 'Acme Corp'),
            customer_tier=customer_profile.get('tier', 'standard'),
            relationship_years=customer_profile.get('relationship_years', 1),
            annual_volume=customer_profile.get('annual_volume', 25000),
            requested_price=anchor_requested_price,
            requested_days=requested_days,
            proposed_price=proposed_price,
            delivery_date=delivery_date,
        )

        try:
            agent_run = run_prebuilt_tool_agent(
                llm=self.llm,
                system_prompt=(
                    'You are a Sales Agent. Use sales tools to inspect customer profile, '
                    'deal sensitivity, counter-offer viability, and total deal value.'
                ),
                user_prompt=user_prompt,
                tools=get_langchain_tools(
                    self.inventory_manager,
                    order,
                    proposed_price,
                    requested_days,
                ),
                response_schema=SalesAgentOutput,
                agent_name='sales_agent',
            )
            response_text = agent_run['response_text']
            logger.info('[%s] Analysis: %s...', self.name, response_text[:200])

            fallback = self._fallback(
                anchor_requested_price,
                proposed_price,
                customer_profile,
                agent_run.get('tool_results') or {
                    'lookup_customer_profile': customer_profile,
                    'assess_deal_sensitivity': sensitivity,
                    'calculate_counter_offer': counter,
                    'calculate_deal_value': deal_value,
                },
            )
            analysis = dict(fallback)
            analysis.update(agent_run.get('structured_response') or {})
            return {
                'agent': self.name,
                'can_proceed': self._as_bool(analysis.get('can_proceed'), fallback.get('can_proceed', False)),
                'agreed_price': self._as_float(analysis.get('agreed_price'), float(fallback.get('agreed_price', proposed_price))),
                'reasoning': analysis.get('reasoning', response_text),
                'analysis': response_text,
                'confidence': self._as_float(analysis.get('confidence'), float(fallback.get('confidence', 0.82))),
                'tool_results': fallback.get('tool_results', {}),
                'used_tools': agent_run.get('used_tools', []),
            }
        except Exception as exc:
            logger.error('[%s] Error: %s', self.name, str(exc))
            fallback = self._fallback(
                anchor_requested_price,
                proposed_price,
                customer_profile,
                {
                    'lookup_customer_profile': customer_profile,
                    'assess_deal_sensitivity': sensitivity,
                    'calculate_counter_offer': counter,
                    'calculate_deal_value': deal_value,
                },
            )
            fallback['reasoning'] = f"Error in analysis: {str(exc)}"
            fallback['analysis'] = str(exc)
            return fallback

    def _fallback(
        self,
        requested_price: float,
        proposed_price: float,
        customer_profile: Dict,
        tool_results: Dict | None = None,
    ) -> Dict:
        tool_results = dict(tool_results or {})
        customer_profile = tool_results.get('lookup_customer_profile') or customer_profile
        sensitivity = tool_results.get('assess_deal_sensitivity')
        if isinstance(sensitivity, list):
            sensitivity = sensitivity[-1] if sensitivity else None
        if not sensitivity:
            sensitivity = assess_deal_sensitivity(customer_profile, requested_price, proposed_price, 18, 18)
            tool_results['assess_deal_sensitivity'] = sensitivity

        counter = tool_results.get('calculate_counter_offer')
        if isinstance(counter, list):
            counter = counter[-1] if counter else None
        if not counter:
            counter = calculate_counter_offer(requested_price, proposed_price, sensitivity)
            tool_results['calculate_counter_offer'] = counter

        deal_value = tool_results.get('calculate_deal_value')
        if isinstance(deal_value, list):
            deal_value = deal_value[-1] if deal_value else None
        if not deal_value:
            deal_value = calculate_deal_value(float(counter.get('counter_offer', proposed_price)), 1)
            tool_results['calculate_deal_value'] = deal_value

        max_acceptable = requested_price * float(customer_profile.get('max_price_uplift', 0.20))
        max_acceptable = max_acceptable + requested_price
        agreed_price = float(counter.get('counter_offer', proposed_price))
        can_proceed = proposed_price <= max_acceptable and float(counter.get('customer_acceptance_likelihood', 0.0)) >= 0.7
        return {
            'can_proceed': can_proceed,
            'agreed_price': agreed_price if can_proceed else min(agreed_price, max_acceptable),
            'reasoning': 'Fallback customer acceptance model applied.',
            'confidence': float(counter.get('customer_acceptance_likelihood', 0.8 if can_proceed else 0.6)),
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

    def _as_bool(self, value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        raw = str(value).strip().lower()
        if raw in {'1', 'true', 'yes', 'approved', 'ok'}:
            return True
        if raw in {'0', 'false', 'no', 'rejected', 'blocked'}:
            return False
        return default
