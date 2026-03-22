import json
import logging
from typing import Dict, List, TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ..tool_calling import run_prebuilt_tool_agent
from .tools import (
    build_material_requirements,
    get_langchain_tools,
    query_alternate_supplier,
    query_supplier_inventory,
    reserve_materials,
    submit_purchase_order,
)

if TYPE_CHECKING:
    from ..runtime.inventory import InventoryManager


logger = logging.getLogger(__name__)


class ProcurementAgentOutput(BaseModel):
    can_proceed: bool | str = False
    reasoning: str = ''
    material_availability: Dict[str, Dict] = Field(default_factory=dict)
    total_cost: float | str = 0.0
    confidence: float | str = 0.7


class LLMProcurementAgent:
    """LLM agent responsible for availability and material cost checks."""

    def __init__(self, llm: ChatOpenAI, inventory_manager: 'InventoryManager'):
        self.llm = llm
        self.inventory_manager = inventory_manager
        self.name = 'Procurement Agent'
        self.prompt = ChatPromptTemplate.from_template(
            """
You are a Procurement Agent responsible for checking material availability and calculating costs.

Current Inventory Data:
{inventory}

Product BOM Data:
{materials}

Task: Analyze the following order request and provide:
1. Whether all materials are available
2. Total material cost
3. Whether supplier replenishment can close any shortfall
4. Any concerns or notes
5. Your confidence level (0.0-1.0)

Order Request:
- Product SKU: {product_sku}
- Quantity: {quantity}
- Requested Delivery Days: {requested_delivery_days}

Provide your analysis in JSON format with keys: can_proceed, reasoning, material_availability, total_cost, confidence
"""
        )

    def invoke(self, order: dict, inventory: List[dict], materials: List[dict]) -> Dict:
        logger.info('[%s] Analyzing availability for %s x%s', self.name, order['product_sku'], order['quantity'])

        deterministic = self._deterministic_inventory_check(order)
        user_prompt = self.prompt.format(
            inventory=json.dumps(inventory, indent=2),
            materials=json.dumps(materials, indent=2),
            product_sku=order['product_sku'],
            quantity=order['quantity'],
            requested_delivery_days=int(order.get('requested_delivery_days') or 18),
        )

        try:
            agent_run = run_prebuilt_tool_agent(
                llm=self.llm,
                system_prompt=(
                    'You are a Procurement Agent. Use available procurement tools before making a decision. '
                    'Base your final recommendation on tool results and inventory facts.'
                ),
                user_prompt=user_prompt,
                tools=get_langchain_tools(self.inventory_manager, order),
                response_schema=ProcurementAgentOutput,
                agent_name='procurement_agent',
            )
            response_text = agent_run['response_text']
            logger.info('[%s] Analysis: %s...', self.name, response_text[:200])

            deterministic = self._deterministic_inventory_check(order, agent_run.get('tool_results') or {})
            analysis = dict(deterministic)
            analysis.update(agent_run.get('structured_response') or {})
            llm_reasoning = analysis.get('reasoning', response_text)
            final_reasoning = (
                deterministic.get('reasoning', llm_reasoning)
                if not deterministic['can_proceed']
                else llm_reasoning
            )
            return {
                'agent': self.name,
                # Procurement gate should be grounded in deterministic inventory math.
                'can_proceed': deterministic['can_proceed'],
                'reasoning': final_reasoning,
                'llm_reasoning': llm_reasoning,
                'analysis': response_text,
                'confidence': float(analysis.get('confidence', 0.7)),
                'total_cost': float(deterministic.get('total_cost', 0) or 0),
                'material_availability': deterministic.get('material_availability', {}),
                'tool_results': deterministic.get('tool_results', {}),
                'used_tools': agent_run.get('used_tools', []),
                'decision_source': 'deterministic_inventory',
            }
        except Exception as exc:
            logger.error('[%s] Error: %s', self.name, str(exc))
            return {
                'agent': self.name,
                'can_proceed': deterministic['can_proceed'],
                'reasoning': f"LLM error: {str(exc)}. {deterministic.get('reasoning', '')}",
                'llm_reasoning': str(exc),
                'analysis': str(exc),
                'confidence': float(deterministic.get('confidence', 0.7)),
                'total_cost': float(deterministic.get('total_cost', 0) or 0),
                'material_availability': deterministic.get('material_availability', {}),
                'tool_results': deterministic.get('tool_results', {}),
                'decision_source': 'deterministic_inventory',
            }

    def _deterministic_inventory_check(self, order: dict, tool_results: Dict | None = None) -> Dict:
        tool_results = dict(tool_results or {})
        sku = order.get('product_sku')
        quantity = int(order.get('quantity') or 0)
        requested_delivery_days = int(order.get('requested_delivery_days') or 18)
        requirements = tool_results.get('build_material_requirements') or build_material_requirements(order, self.inventory_manager)
        tool_results['build_material_requirements'] = requirements
        if not requirements.get('materials'):
            return {
                'can_proceed': False,
                'reasoning': f'Product SKU "{sku}" not found in material BOM.',
                'confidence': 0.95,
                'total_cost': 0.0,
                'material_availability': {},
                'tool_results': tool_results,
            }

        material_availability = requirements.get('materials', {})
        total_cost = round(sum(item.get('line_cost', 0.0) for item in material_availability.values()), 2)
        shortages = {mid: info for mid, info in material_availability.items() if not info.get('is_available', False)}
        can_proceed = not shortages
        if can_proceed:
            reasoning = 'All required materials are available in inventory.'
            confidence = 0.93
            tool_results['inventory_only'] = {'feasible_quantity': requirements.get('feasible_quantity', quantity)}
        else:
            primary_supplier = self.inventory_manager.procurement_policy.get('primary_supplier', 'Primary Supplier')
            primary_result = tool_results.get('query_supplier_inventory')
            if isinstance(primary_result, list):
                primary_result = next(
                    (item for item in primary_result if item.get('supplier') == primary_supplier),
                    primary_result[-1] if primary_result else None,
                )
            if not primary_result:
                primary_result = query_supplier_inventory(self.inventory_manager, shortages, primary_supplier)
                tool_results['query_supplier_inventory'] = primary_result

            alternate_result = tool_results.get('query_alternate_supplier')
            if isinstance(alternate_result, list):
                alternate_result = alternate_result[-1] if alternate_result else None
            if not alternate_result:
                alternate_result = query_alternate_supplier(self.inventory_manager, shortages)
                tool_results['query_alternate_supplier'] = alternate_result
            primary_lead_time = int(primary_result.get('lead_time_days') or 0)
            alternate_lead_time = int(alternate_result.get('lead_time_days') or 0)
            buffer_days = 2

            if primary_result.get('can_fulfill') and requested_delivery_days >= primary_lead_time + buffer_days:
                can_proceed = True
                reservation = tool_results.get('reserve_materials')
                if isinstance(reservation, list):
                    reservation = next(
                        (item for item in reservation if item.get('supplier') == primary_supplier),
                        reservation[-1] if reservation else None,
                    )
                if not reservation:
                    reservation = reserve_materials(self.inventory_manager, primary_result)
                    tool_results['reserve_materials'] = reservation

                purchase_order = tool_results.get('submit_purchase_order')
                if isinstance(purchase_order, list):
                    purchase_order = next(
                        (item for item in purchase_order if item.get('supplier') == primary_supplier),
                        purchase_order[-1] if purchase_order else None,
                    )
                if not purchase_order:
                    purchase_order = submit_purchase_order(
                        self.inventory_manager,
                        primary_supplier,
                        reservation.get('reserved_materials', {}),
                    )
                    tool_results['submit_purchase_order'] = purchase_order
                reasoning = (
                    f'Current inventory is short for {", ".join(shortages.keys())}, but {primary_supplier} can replenish '
                    f'the missing material within {primary_lead_time} days and keep the order feasible.'
                )
                confidence = 0.86
                total_cost = round(total_cost + float(purchase_order.get('total_cost') or 0.0), 2)
            elif alternate_result.get('can_fulfill') and requested_delivery_days >= alternate_lead_time + buffer_days:
                can_proceed = True
                alternate_supplier = alternate_result.get('supplier')
                reservation = tool_results.get('reserve_materials')
                if isinstance(reservation, list):
                    reservation = next(
                        (item for item in reservation if item.get('supplier') == alternate_supplier),
                        reservation[-1] if reservation else None,
                    )
                if not reservation:
                    reservation = reserve_materials(self.inventory_manager, alternate_result)
                    tool_results['reserve_materials'] = reservation

                purchase_order = tool_results.get('submit_purchase_order')
                if isinstance(purchase_order, list):
                    purchase_order = next(
                        (item for item in purchase_order if item.get('supplier') == alternate_supplier),
                        purchase_order[-1] if purchase_order else None,
                    )
                if not purchase_order:
                    purchase_order = submit_purchase_order(
                        self.inventory_manager,
                        alternate_supplier,
                        reservation.get('reserved_materials', {}),
                    )
                    tool_results['submit_purchase_order'] = purchase_order
                reasoning = (
                    f'Current inventory is short for {", ".join(shortages.keys())}, but {alternate_supplier} can replenish '
                    f'the shortage within {alternate_lead_time} days and support the requested schedule.'
                )
                confidence = 0.82
                total_cost = round(total_cost + float(purchase_order.get('total_cost') or 0.0), 2)
            else:
                reasoning = (
                    f'Insufficient inventory for: {", ".join(shortages.keys())}. '
                    f'Earliest realistic replenishment is {primary_lead_time + buffer_days} days.'
                )
                confidence = 0.9

        return {
            'can_proceed': can_proceed,
            'reasoning': reasoning,
            'confidence': confidence,
            'total_cost': round(total_cost, 2),
            'material_availability': material_availability,
            'tool_results': tool_results,
        }
