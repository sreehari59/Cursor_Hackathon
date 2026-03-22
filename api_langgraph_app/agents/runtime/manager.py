import json
import logging
import os
from datetime import datetime
from typing import Dict

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..finance import LLMFinanceAgent
from ..logistics import LLMLogisticsAgent
from ..procurement import LLMProcurementAgent
from ..production import LLMProductionAgent
from ..sales import LLMSalesAgent
from .inventory import InventoryManager
from .models import LLMAgentState, OrderRequest


logger = logging.getLogger(__name__)
MIN_CONSENSUS_CONFIDENCE = float(os.getenv('MIN_CONSENSUS_CONFIDENCE', '0.70'))


def _normalize_confidence(value, default=0.0):
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = float(default)
    if raw > 1.0:
        raw = raw / 100.0
    return max(0.0, min(1.0, raw))


class LLMManagerAgent:
    """LangGraph manager orchestrating procurement, production, logistics, finance, and sales."""

    def __init__(self, api_key: str, inventory_manager: InventoryManager):
        self.llm = ChatOpenAI(api_key=api_key, model='gpt-3.5-turbo', temperature=0.3)
        self.inventory_manager = inventory_manager
        self.procurement_agent = LLMProcurementAgent(self.llm, inventory_manager)
        self.production_agent = LLMProductionAgent(self.llm, inventory_manager)
        self.logistics_agent = LLMLogisticsAgent(self.llm, inventory_manager)
        self.finance_agent = LLMFinanceAgent(self.llm, inventory_manager)
        self.sales_agent = LLMSalesAgent(self.llm, inventory_manager)
        self.name = 'Manager Agent'
        self.graph = self._build_graph()

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(LLMAgentState)

        workflow.add_node('procurement', self._procurement_node)
        workflow.add_node('production', self._production_node)
        workflow.add_node('logistics', self._logistics_node)
        workflow.add_node('finance', self._finance_node)
        workflow.add_node('sales', self._sales_node)
        workflow.add_node('consensus', self._consensus_node)

        workflow.set_entry_point('procurement')
        workflow.add_edge('procurement', 'production')
        workflow.add_edge('production', 'logistics')
        workflow.add_edge('logistics', 'finance')
        workflow.add_edge('finance', 'sales')
        workflow.add_edge('sales', 'consensus')
        workflow.add_edge('consensus', END)

        return workflow.compile()

    def _procurement_node(self, state: LLMAgentState) -> LLMAgentState:
        logger.info('[STEP 1] Procurement Agent Evaluation')
        result = self.procurement_agent.invoke(state['order'], state['inventory'], state['materials'])
        state['procurement_analysis'] = json.dumps(result)
        state['messages'].append(AIMessage(content=f"Procurement: {result['reasoning']}"))
        logger.info('  Result: %s', result['reasoning'])
        logger.info('  Confidence: %.0f%%', result['confidence'] * 100)
        return state

    def _production_node(self, state: LLMAgentState) -> LLMAgentState:
        logger.info('[STEP 2] Production Agent Evaluation')
        result = self.production_agent.invoke(state['order'])
        state['production_analysis'] = json.dumps(result)
        state['messages'].append(AIMessage(content=f"Production: {result['reasoning']}"))
        logger.info('  Result: %s', result['reasoning'])
        logger.info('  Production Days: %s', result.get('production_days'))
        logger.info('  Confidence: %.0f%%', result['confidence'] * 100)
        return state

    def _logistics_node(self, state: LLMAgentState) -> LLMAgentState:
        logger.info('[STEP 3] Logistics Agent Evaluation')

        procurement_data = json.loads(state['procurement_analysis'] or '{}')
        production_data = json.loads(state['production_analysis'] or '{}')
        material_cost = float(procurement_data.get('total_cost') or 100000)
        production_days = int(production_data.get('production_days') or 14)

        result = self.logistics_agent.invoke(state['order'], material_cost, production_days)
        state['logistics_analysis'] = json.dumps(result)
        state['messages'].append(AIMessage(content=f"Logistics: {result['reasoning']}"))

        logger.info('  Result: %s', result['reasoning'])
        logger.info('  Delivery Date: %s', result['delivery_date'])
        logger.info('  Confidence: %.0f%%', result['confidence'] * 100)
        return state

    def _finance_node(self, state: LLMAgentState) -> LLMAgentState:
        logger.info('[STEP 4] Finance Agent Evaluation')

        procurement_data = json.loads(state['procurement_analysis'] or '{}')
        production_data = json.loads(state['production_analysis'] or '{}')
        logistics_data = json.loads(state['logistics_analysis'] or '{}')
        result = self.finance_agent.invoke(state['order'], procurement_data, production_data, logistics_data)

        state['finance_analysis'] = json.dumps(result)
        state['messages'].append(AIMessage(content=f"Finance: {result['reasoning']}"))

        logger.info('  Result: %s', result['reasoning'])
        logger.info('  Final Price: %s', result.get('final_price'))
        logger.info('  Confidence: %.0f%%', result['confidence'] * 100)
        return state

    def _sales_node(self, state: LLMAgentState) -> LLMAgentState:
        logger.info('[STEP 5] Sales Agent Evaluation')

        finance_data = json.loads(state['finance_analysis'] or '{}')
        logistics_data = json.loads(state['logistics_analysis'] or '{}')
        result = self.sales_agent.invoke(state['order'], finance_data, logistics_data)

        state['sales_analysis'] = json.dumps(result)
        state['messages'].append(AIMessage(content=f"Sales: {result['reasoning']}"))

        logger.info('  Result: %s', result['reasoning'])
        logger.info('  Agreed Price: %s', result.get('agreed_price'))
        logger.info('  Confidence: %.0f%%', result['confidence'] * 100)
        return state

    def _consensus_node(self, state: LLMAgentState) -> LLMAgentState:
        logger.info('[STEP 6] Consensus Check')

        procurement_data = json.loads(state['procurement_analysis'] or '{}')
        production_data = json.loads(state['production_analysis'] or '{}')
        logistics_data = json.loads(state['logistics_analysis'] or '{}')
        finance_data = json.loads(state['finance_analysis'] or '{}')
        sales_data = json.loads(state['sales_analysis'] or '{}')

        all_can_proceed = all(
            [
                procurement_data.get('can_proceed', False),
                production_data.get('can_proceed', False),
                logistics_data.get('can_proceed', False),
                finance_data.get('can_proceed', False),
                sales_data.get('can_proceed', False),
            ]
        )

        avg_confidence = (
            _normalize_confidence(procurement_data.get('confidence', 0), 0)
            + _normalize_confidence(production_data.get('confidence', 0), 0)
            + _normalize_confidence(logistics_data.get('confidence', 0), 0)
            + _normalize_confidence(finance_data.get('confidence', 0), 0)
            + _normalize_confidence(sales_data.get('confidence', 0), 0)
        ) / 5

        consensus_reached = all_can_proceed and avg_confidence >= MIN_CONSENSUS_CONFIDENCE

        logger.info('  All Agents Can Proceed: %s', all_can_proceed)
        logger.info('  Average Confidence: %.0f%%', avg_confidence * 100)
        logger.info('  Consensus Reached: %s', consensus_reached)

        state['all_can_proceed'] = consensus_reached
        state['final_decision'] = 'SUCCESS' if consensus_reached else 'FAILURE'
        return state

    def process_order(self, request: OrderRequest) -> Dict:
        logger.info('\n%s', '=' * 60)
        logger.info('[%s] Processing Order: %s', self.name, request.order_id)
        logger.info(
            '[%s] Request: %s x%s to %s',
            self.name,
            request.product_sku,
            request.quantity,
            request.customer_location,
        )
        logger.info('%s\n', '=' * 60)

        initial_state: LLMAgentState = {
            'order': {
                'order_id': request.order_id,
                'product_sku': request.product_sku,
                'quantity': request.quantity,
                'customer_location': request.customer_location,
                'requested_price': request.requested_price,
                'requested_delivery_days': request.requested_delivery_days,
                'customer': request.customer,
                'priority': request.priority,
                'negotiation_context': request.negotiation_context or {},
            },
            'inventory': self.inventory_manager.inventory,
            'materials': self.inventory_manager.materials,
            'procurement_analysis': None,
            'production_analysis': None,
            'logistics_analysis': None,
            'finance_analysis': None,
            'sales_analysis': None,
            'messages': [HumanMessage(content=f'Process order: {request.order_id}')],
            'all_can_proceed': False,
            'final_decision': None,
        }

        final_state = self.graph.invoke(initial_state)
        return self._generate_final_response(request, final_state)

    def _generate_final_response(self, request: OrderRequest, state: LLMAgentState) -> Dict:
        procurement_data = json.loads(state['procurement_analysis'] or '{}')
        production_data = json.loads(state['production_analysis'] or '{}')
        logistics_data = json.loads(state['logistics_analysis'] or '{}')
        finance_data = json.loads(state['finance_analysis'] or '{}')
        sales_data = json.loads(state['sales_analysis'] or '{}')

        final_price = float(sales_data.get('agreed_price') or finance_data.get('final_price') or 0)
        if request.quantity > 0:
            total_deal_value = round(final_price * request.quantity, 2)
        else:
            total_deal_value = round(float(finance_data.get('total_deal_value') or 0), 2)

        if not state['all_can_proceed']:
            agent_responses = {
                'procurement': procurement_data,
                'production': production_data,
                'logistics': logistics_data,
                'finance': finance_data,
                'sales': sales_data,
            }
            rejection_reason = 'Order cannot be processed. Consensus not reached.'
            for agent_id in ['procurement', 'production', 'logistics', 'finance', 'sales']:
                agent_response = agent_responses.get(agent_id) or {}
                if not agent_response.get('can_proceed', False):
                    rejection_reason = agent_response.get('reasoning') or rejection_reason
                    break

            return {
                'status': 'FAILURE',
                'order_id': request.order_id,
                'product_sku': request.product_sku,
                'quantity': request.quantity,
                'customer_location': request.customer_location,
                'message': rejection_reason,
                'consensus_reached': False,
                'agent_responses': agent_responses,
                'timestamp': datetime.now().isoformat(),
            }

        response = {
            'status': 'SUCCESS',
            'order_id': request.order_id,
            'product_sku': request.product_sku,
            'quantity': request.quantity,
            'customer_location': request.customer_location,
            'final_price': final_price,
            'total_deal_value': total_deal_value,
            'delivery_date': logistics_data.get('delivery_date', ''),
            'cost_breakdown': {
                'discount_rate': finance_data.get('discount_rate', 0),
                'profit_margin': finance_data.get('margin', 0.25),
            },
            'consensus_reached': True,
            'agent_responses': {
                'procurement': procurement_data,
                'production': production_data,
                'logistics': logistics_data,
                'finance': finance_data,
                'sales': sales_data,
            },
            'timestamp': datetime.now().isoformat(),
        }

        logger.info('\n%s', '=' * 60)
        logger.info('FINAL RESPONSE:')
        logger.info('%s', '=' * 60)
        logger.info(json.dumps(response, indent=2))
        logger.info('%s\n', '=' * 60)
        return response
