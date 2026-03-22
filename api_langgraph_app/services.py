import json
import logging
import os
import time
from datetime import datetime

from .agents import AGENT_IDS
from .agents.runtime import OrderRequest, build_mock_process_order_response
from .constants import BASELINE
from . import state

logger = logging.getLogger(__name__)
MIN_CONSENSUS_CONFIDENCE = float(os.getenv('MIN_CONSENSUS_CONFIDENCE', '0.70'))


def safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_confidence(value, default=0.0):
    raw = safe_float(value, default)
    if raw > 1.0:
        raw = raw / 100.0
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


def stabilize_agent_confidence(agent_response, fallback=0.78):
    normalized = normalize_confidence(agent_response.get('confidence', fallback), fallback)
    if bool(agent_response.get('can_proceed', False)) and normalized < 0.70:
        normalized = fallback
    agent_response['confidence'] = normalized
    return agent_response


def normalize_priority(priority):
    normalized = str(priority or 'standard').lower()
    if normalized in ['rush', 'critical', 'expedited']:
        return 'expedited'
    return 'normal'


def build_synk_order(payload):
    timestamp_suffix = str(int(time.time() * 1000))[-3:]
    order = {
        'id': payload.get('id') or payload.get('order_id') or f'ORD-RUSH-{timestamp_suffix}',
        'customer': payload.get('customer', 'Acme Corp'),
        'product': payload.get('product') or payload.get('product_sku', 'PMP-STD-100'),
        'quantity': safe_int(payload.get('quantity'), 5000),
        'requestedPrice': safe_float(payload.get('requestedPrice', payload.get('requested_price')), 10.0),
        'requestedDeliveryDays': safe_int(payload.get('requestedDeliveryDays', payload.get('requested_delivery_days')), 18),
        'priority': str(payload.get('priority', 'rush')).lower(),
        'customerLocation': resolve_customer_location(payload),
    }
    incoming_context = dict(payload.get('negotiationContext') or payload.get('negotiation_context') or {})
    order['negotiationContext'] = {
        **incoming_context,
        'original_requested_price': safe_float(incoming_context.get('original_requested_price'), order['requestedPrice']),
        'original_requested_delivery_days': safe_int(
            incoming_context.get('original_requested_delivery_days'),
            order['requestedDeliveryDays'],
        ),
        'original_quantity': safe_int(incoming_context.get('original_quantity'), order['quantity']),
        'round_number': safe_int(incoming_context.get('round_number'), 1),
        'round_goal': incoming_context.get('round_goal', 'Evaluate the customer request as submitted.'),
    }
    return order


def resolve_customer_location(payload):
    explicit_location = payload.get('customer_location')
    if explicit_location:
        return explicit_location

    customer = str(payload.get('customer', '')).lower()
    if 'local' in customer:
        return 'local city'
    if 'regional' in customer:
        return 'regional state'
    return 'national'


def build_process_payload_from_order(order, base_payload=None):
    base_payload = dict(base_payload or {})
    payload = {
        'id': order.get('id'),
        'customer': order.get('customer'),
        'product': order.get('product'),
        'quantity': safe_int(order.get('quantity'), 1),
        'requestedPrice': safe_float(order.get('requestedPrice'), 10.0),
        'requestedDeliveryDays': safe_int(order.get('requestedDeliveryDays'), 18),
        'priority': order.get('priority', 'normal'),
        'customer_location': order.get('customerLocation') or base_payload.get('customer_location'),
        'negotiationContext': dict(order.get('negotiationContext') or {}),
    }
    if not payload['customer_location']:
        payload['customer_location'] = resolve_customer_location(base_payload or payload)
    return payload


def get_blocking_agents(process_response):
    agent_responses = (process_response or {}).get('agent_responses') or {}
    if not isinstance(agent_responses, dict):
        return []
    return [agent_id for agent_id in AGENT_IDS if not bool((agent_responses.get(agent_id) or {}).get('can_proceed', False))]


def run_process_order_for_synk(order, payload):
    order_request = OrderRequest(
        order_id=order['id'],
        product_sku=order['product'],
        quantity=max(1, safe_int(order['quantity'], 1)),
        customer_location=resolve_customer_location(payload),
        priority=normalize_priority(order.get('priority')),
        customer=order.get('customer', 'Acme Corp'),
        requested_price=safe_float(order.get('requestedPrice'), 10.0),
        requested_delivery_days=safe_int(order.get('requestedDeliveryDays'), 18),
        negotiation_context=dict(payload.get('negotiationContext') or payload.get('negotiation_context') or order.get('negotiationContext') or {}),
    )

    use_mock_process_order = str(os.getenv('BACKEND_USE_MOCK_PROCESS_ORDER', 'false')).strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }

    if use_mock_process_order:
        logger.info(
            'process_order running in mock mode. live_agent_pipeline_enabled=%s',
            all(
                [
                    state.procurement_agent is not None,
                    state.production_agent is not None,
                    state.logistics_agent is not None,
                    state.finance_agent is not None,
                    state.sales_agent is not None,
                    state.inventory_manager is not None,
                ]
            ),
        )
        if all(
            [
                state.procurement_agent is not None,
                state.production_agent is not None,
                state.logistics_agent is not None,
                state.finance_agent is not None,
                state.sales_agent is not None,
                state.inventory_manager is not None,
            ]
        ):
            response = run_live_agent_pipeline(order_request)
            return response, (
                'Using live multi-agent pipeline while BACKEND_USE_MOCK_PROCESS_ORDER=true '
                '(manager disabled, agent-by-agent execution enabled).'
            )

        response = build_mock_process_order_response(order_request)
        return response, 'Using mock process_order response (live agent pipeline unavailable).'

    if state.manager is None:
        return {
            'status': 'FAILURE',
            'order_id': order_request.order_id,
            'product_sku': order_request.product_sku,
            'quantity': int(order_request.quantity),
            'customer_location': order_request.customer_location,
            'message': 'LangGraph manager unavailable. Enable a valid OpenAI key and disable mock mode only when manager initialization succeeds.',
            'consensus_reached': False,
            'agent_responses': {},
            'mock_mode': False,
            'timestamp': datetime.utcnow().isoformat(),
        }, 'LangGraph manager unavailable; no mock fallback because BACKEND_USE_MOCK_PROCESS_ORDER=false.'

    response = state.manager.process_order(order_request)
    response['mock_mode'] = False
    response['live_agents'] = AGENT_IDS
    return response, None


def _build_live_order_dict(order_request):
    return {
        'order_id': order_request.order_id,
        'product_sku': order_request.product_sku,
        'quantity': order_request.quantity,
        'customer_location': order_request.customer_location,
        'priority': order_request.priority,
        'customer': order_request.customer,
        'requested_price': order_request.requested_price,
        'requested_delivery_days': order_request.requested_delivery_days,
        'negotiation_context': order_request.negotiation_context or {},
    }


def run_live_agent_pipeline(order_request):
    order = _build_live_order_dict(order_request)

    logger.info(
        'Invoking live agent pipeline for order=%s sku=%s qty=%s',
        order_request.order_id,
        order_request.product_sku,
        order_request.quantity,
    )

    procurement_result = state.procurement_agent.invoke(
        order,
        state.inventory_manager.inventory,
        state.inventory_manager.materials,
    )
    production_result = state.production_agent.invoke(order)
    logistics_result = state.logistics_agent.invoke(
        order,
        float(procurement_result.get('total_cost') or 0.0),
        int(production_result.get('production_days') or 14),
    )
    finance_result = state.finance_agent.invoke(order, procurement_result, production_result, logistics_result)
    sales_result = state.sales_agent.invoke(order, finance_result, logistics_result)

    agent_responses = {
        'procurement': stabilize_agent_confidence(procurement_result, 0.85),
        'production': stabilize_agent_confidence(production_result, 0.82),
        'logistics': stabilize_agent_confidence(logistics_result, 0.80),
        'finance': stabilize_agent_confidence(finance_result, 0.82),
        'sales': stabilize_agent_confidence(sales_result, 0.80),
    }

    all_can_proceed = all(bool(agent_responses[agent_id].get('can_proceed', False)) for agent_id in AGENT_IDS)
    avg_confidence = (
        sum(normalize_confidence(agent_responses[agent_id].get('confidence', 0.0), 0.0) for agent_id in AGENT_IDS)
        / len(AGENT_IDS)
    )
    consensus_reached = all_can_proceed and avg_confidence >= MIN_CONSENSUS_CONFIDENCE

    final_price = safe_float(
        sales_result.get('agreed_price', finance_result.get('final_price', order_request.requested_price)),
        order_request.requested_price,
    )
    total_deal_value = round(final_price * max(1, int(order_request.quantity)), 2)
    delivery_date = logistics_result.get('delivery_date', '')

    rejection_reason = None
    if not consensus_reached:
        for agent_id in AGENT_IDS:
            if not bool(agent_responses[agent_id].get('can_proceed', False)):
                rejection_reason = agent_responses[agent_id].get('reasoning')
                break
        if rejection_reason is None:
            rejection_reason = 'Consensus confidence threshold not met.'

    response = {
        'status': 'SUCCESS' if consensus_reached else 'FAILURE',
        'order_id': order_request.order_id,
        'product_sku': order_request.product_sku,
        'quantity': int(order_request.quantity),
        'customer_location': order_request.customer_location,
        'final_price': final_price,
        'total_deal_value': total_deal_value,
        'delivery_date': delivery_date,
        'cost_breakdown': {
            'discount_rate': safe_float(finance_result.get('discount_rate', 0.0), 0.0),
            'profit_margin': safe_float(finance_result.get('margin', 0.22), 0.22),
        },
        'consensus_reached': consensus_reached,
        'message': None if consensus_reached else rejection_reason,
        'agent_responses': agent_responses,
        'live_agents': AGENT_IDS,
        'mock_mode': False,
        'timestamp': datetime.utcnow().isoformat(),
    }

    logger.info(
        'Live agent pipeline completed for order=%s consensus=%s confidence=%.2f',
        order_request.order_id,
        consensus_reached,
        avg_confidence,
    )
    return response


def agent_status_and_approval(agent_id, round_number):
    if round_number == 1 and agent_id == 'finance':
        return 'objecting', False
    if round_number < 3:
        return 'proposing', True
    return 'agreed', True


def mock_agent_proposal(agent_id, order, round_number, previous_round=None):
    status, approved = agent_status_and_approval(agent_id, round_number)
    requested_price = safe_float(order.get('requestedPrice'), 10.0)
    requested_days = safe_int(order.get('requestedDeliveryDays'), 18)

    if round_number == 1:
        target_price = requested_price
        target_days = requested_days
        margin = 12.4
    elif round_number == 2:
        target_price = requested_price
        target_days = requested_days
        margin = 17.2
    else:
        target_price = requested_price
        target_days = requested_days
        margin = 20.6

    previous_round_ref = previous_round.get('round') if isinstance(previous_round, dict) else None
    reasoning = {
        'production': f"Capacity aligned for {order.get('quantity', 5000)} units in {target_days} days with controlled overtime.",
        'finance': f"Margin check at ${target_price:.2f}/unit -> {margin:.1f}% margin {'meets' if approved else 'below'} floor.",
        'logistics': f"Ground freight supports {target_days}-day commitment with reliable carrier availability.",
        'procurement': f"Supplier {BASELINE['primarySupplier']} confirms material reservation for requested quantity.",
        'sales': f"Strategic account posture supports negotiated terms at ${target_price:.2f}/unit.",
    }.get(agent_id, 'Agent analysis complete.')

    actions = [
        {
            'kind': 'tool_call',
            'label': f'{agent_id}_analyze()',
            'detail': f"Round {round_number} analysis started for order {order.get('id', 'ORD-RUSH-001')}.",
            'data': {'round': round_number, 'previous_round': previous_round_ref or 0},
        },
        {
            'kind': 'tool_result',
            'label': f'{agent_id}_result',
            'detail': f'Computed position at ${target_price:.2f} and {target_days} delivery days.',
            'data': {'price': target_price, 'delivery_days': target_days, 'margin': margin},
        },
        {
            'kind': 'objection' if not approved else 'agreement',
            'label': 'position',
            'detail': reasoning,
        },
    ]

    return {
        'agentId': agent_id,
        'round': round_number,
        'status': status,
        'reasoning': reasoning,
        'metrics': {
            'price': round(target_price, 2),
            'deliveryDays': target_days,
            'margin': round(margin, 1),
            'quantity': safe_int(order.get('quantity'), 5000),
        },
        'approved': approved,
        'actions': actions,
    }


def build_round_summary(order, round_number, previous_round=None):
    requested_price = safe_float(order.get('requestedPrice'), 10.0)
    requested_days = safe_int(order.get('requestedDeliveryDays'), 18)
    negotiation_context = order.get('negotiationContext') or {}
    strategy_notes = list(negotiation_context.get('strategy_notes') or [])

    if round_number == 1:
        price = requested_price
        delivery_days = requested_days
        margin = 12.4
        overtime_hours = 4
        converged = False
    elif round_number == 2:
        price = requested_price
        delivery_days = requested_days
        margin = max(17.2, safe_float(previous_round.get('margin') if previous_round else 17.2, 17.2))
        overtime_hours = 8 if negotiation_context.get('production_strategy') else 6
        converged = False
    else:
        price = requested_price
        delivery_days = requested_days
        margin = max(20.6, safe_float(previous_round.get('margin') if previous_round else 20.6, 20.6))
        overtime_hours = 10 if negotiation_context.get('production_strategy') else 6
        converged = False

    proposals = [
        mock_agent_proposal(agent_id, order, round_number, previous_round)
        for agent_id in AGENT_IDS
    ]

    return {
        'round': round_number,
        'price': round(price, 2),
        'deliveryDays': delivery_days,
        'margin': margin,
        'shippingMode': 'ground',
        'overtimeHours': overtime_hours,
        'proposals': proposals,
        'converged': converged,
        'order_context': order,
        'strategy': {
            'goal': negotiation_context.get('round_goal'),
            'productionStrategy': negotiation_context.get('production_strategy'),
            'revenueGoal': negotiation_context.get('revenue_goal'),
            'notes': strategy_notes,
            'blockingAgents': list(negotiation_context.get('blocking_agents') or []),
        },
    }


def _proposal_status(approved, round_number, all_live_approved):
    if approved:
        return 'agreed' if all_live_approved or round_number >= 2 else 'proposing'
    return 'objecting'


def _short_reason(text, fallback='Agent analysis complete.'):
    raw = str(text or '').strip()
    if not raw:
        return fallback
    first_line = raw.splitlines()[0].strip()
    if len(first_line) <= 160:
        return first_line
    return f"{first_line[:157].rstrip()}..."


def _procurement_feasible_quantity(order, live_result):
    requested_quantity = max(1, safe_int(order.get('quantity'), 1))
    material_availability = live_result.get('material_availability') or {}
    feasible_quantities = []

    for item in material_availability.values():
        required = safe_float(item.get('required'), 0)
        available = safe_float(item.get('available'), 0)
        if required <= 0:
            continue
        feasible_quantities.append(int((available * requested_quantity) / required))

    if not feasible_quantities:
        return requested_quantity
    return max(0, min(requested_quantity, min(feasible_quantities)))


def _build_round_specific_proposal(agent_id, live_result, round_number, order, quantity, price, delivery_days, margin, all_live_approved):
    approved = bool(live_result.get('can_proceed', False))
    requested_days = safe_int(order.get('requestedDeliveryDays'), delivery_days)
    requested_price = safe_float(order.get('requestedPrice'), price)
    metrics = {
        'price': round(price, 2),
        'deliveryDays': delivery_days,
        'margin': round(margin, 1),
        'quantity': quantity,
    }
    base_reason = live_result.get('reasoning') or live_result.get('llm_reasoning') or f'{agent_id} analysis completed.'
    reasoning = _short_reason(base_reason)
    stage_label = {1: 'initial_assessment', 2: 'counter_proposal', 3: 'final_position'}.get(round_number, 'assessment')
    stage_detail = {
        1: 'Initial feasibility review completed.',
        2: 'Negotiation round opened to improve terms and resolve blockers.',
        3: 'Final position prepared for consensus and customer callback.',
    }.get(round_number, 'Assessment completed.')

    if round_number == 2:
        if agent_id == 'procurement':
            feasible_quantity = _procurement_feasible_quantity(order, live_result)
            if approved:
                reasoning = f'Inventory is secured. Procurement confirms immediate reservation for {quantity} units.'
            else:
                metrics['quantity'] = feasible_quantity
                metrics['deliveryDays'] = max(delivery_days, requested_days + 7)
                reasoning = (
                    f'Original request remains blocked by material shortage. Counter-proposal: release {feasible_quantity} units now '
                    f'or replenish for full delivery in {metrics["deliveryDays"]} days.'
                )
        elif agent_id == 'production':
            if approved:
                metrics['deliveryDays'] = max(1, delivery_days - 1)
                reasoning = f'Production can support the order and tighten factory completion to {metrics["deliveryDays"]} days.'
            else:
                metrics['deliveryDays'] = max(delivery_days, requested_days + 6)
                reasoning = (
                    f'Original deadline is not feasible. Counter-proposal: phased production over {metrics["deliveryDays"]} days '
                    'with overtime and slot reallocation.'
                )
        elif agent_id == 'logistics':
            if not all_live_approved:
                metrics['deliveryDays'] = max(1, delivery_days - 1)
                reasoning = f'Logistics can offset schedule risk with express routing and target {metrics["deliveryDays"]} days in transit.'
            else:
                reasoning = f'Logistics remains aligned on ground routing for a {metrics["deliveryDays"]}-day commitment.'
        elif agent_id == 'finance':
            revised_price = max(price, requested_price * (1.06 if (not approved or not all_live_approved) else 1.0))
            metrics['price'] = round(revised_price, 2)
            metrics['margin'] = round(max(margin, 18.0 if not approved else margin + 1.0), 1)
            if approved:
                reasoning = f'Finance supports a recovery plan at ${metrics["price"]:.2f}/unit with {metrics["margin"]:.1f}% margin.'
            else:
                reasoning = f'Original commercial terms remain below margin floor. Counter-offer: ${metrics["price"]:.2f}/unit.'
        elif agent_id == 'sales':
            if not all_live_approved:
                metrics['deliveryDays'] = max(delivery_days, requested_days + 2)
                reasoning = (
                    f'Sales can take revised terms back to the customer at ${metrics["price"]:.2f}/unit '
                    f'with {metrics["deliveryDays"]}-day delivery.'
                )
            else:
                reasoning = f'Sales confirms the customer-facing offer at ${metrics["price"]:.2f}/unit.'
    elif round_number == 3:
        if agent_id == 'procurement':
            feasible_quantity = _procurement_feasible_quantity(order, live_result)
            if approved:
                reasoning = f'Final procurement position: materials are fully reserved for {quantity} units.'
            else:
                metrics['quantity'] = feasible_quantity
                metrics['deliveryDays'] = max(delivery_days, requested_days + 14)
                reasoning = (
                    f'Final procurement position: cannot approve {quantity} units from current stock. '
                    f'Best immediate allocation is {feasible_quantity} units or full fulfillment in {metrics["deliveryDays"]} days.'
                )
        elif agent_id == 'production':
            if approved:
                reasoning = f'Final production position: factory schedule locked for {metrics["deliveryDays"]} days.'
            else:
                metrics['deliveryDays'] = max(delivery_days, requested_days + 10)
                reasoning = f'Final production position: earliest reliable completion is {metrics["deliveryDays"]} days.'
        elif agent_id == 'logistics':
            reasoning = (
                f'Final logistics position: {"air" if not all_live_approved else "ground"} routing can support '
                f'the recommended {metrics["deliveryDays"]}-day schedule.'
            )
        elif agent_id == 'finance':
            revised_price = max(metrics['price'], requested_price * (1.08 if not approved else 1.02))
            metrics['price'] = round(revised_price, 2)
            metrics['margin'] = round(max(metrics['margin'], 20.0 if not approved else metrics['margin']), 1)
            reasoning = (
                f'Final finance position: recommended commercial terms are ${metrics["price"]:.2f}/unit '
                f'at {metrics["margin"]:.1f}% margin.'
            )
        elif agent_id == 'sales':
            metrics['deliveryDays'] = max(metrics['deliveryDays'], requested_days if approved else requested_days + 2)
            reasoning = (
                f'Final sales position: communicate ${metrics["price"]:.2f}/unit and '
                f'{metrics["deliveryDays"]}-day delivery to the customer.'
            )

    actions = [
        {
            'kind': 'tool_call',
            'label': f'{agent_id}_{stage_label}()',
            'detail': f'Round {round_number}: {stage_detail}',
            'data': {
                'round': round_number,
                'decision_source': live_result.get('decision_source', 'llm'),
            },
        },
        {
            'kind': 'tool_result',
            'label': f'{agent_id}_position',
            'detail': (
                f"Current position: ${metrics['price']:.2f}/unit, {metrics['deliveryDays']} delivery days, "
                f"quantity {metrics['quantity']}."
            ),
            'data': {
                'price': metrics['price'],
                'delivery_days': metrics['deliveryDays'],
                'quantity': metrics['quantity'],
            },
        },
    ]

    if round_number >= 2:
        actions.append(
            {
                'kind': 'response',
                'label': f'{agent_id}_negotiation_note',
                'detail': reasoning,
                'data': {
                    'status': _proposal_status(approved, round_number, all_live_approved),
                },
            }
        )

    actions.append(
        {
            'kind': 'agreement' if approved else 'objection',
            'label': f'{agent_id}_verdict',
            'detail': reasoning,
            'data': {
                'can_proceed': approved,
            },
        }
    )

    return {
        'status': _proposal_status(approved, round_number, all_live_approved),
        'reasoning': reasoning,
        'metrics': metrics,
        'approved': approved,
        'actions': actions,
    }


def apply_live_agent_results_to_round(round_summary, process_response):
    """
    Override round proposals with live process_order agent outputs when available.
    """
    if not isinstance(process_response, dict):
        return round_summary

    live_agent_responses = process_response.get('agent_responses') or {}
    if not isinstance(live_agent_responses, dict):
        return round_summary

    proposals = list(round_summary.get('proposals') or [])
    all_live_approved = True
    live_found = False
    round_number = safe_int(round_summary.get('round'), 1)

    for proposal in proposals:
        agent_id = proposal.get('agentId')
        live_result = live_agent_responses.get(agent_id)
        if isinstance(live_result, dict) and not bool(live_result.get('can_proceed', False)):
            all_live_approved = False
            break

    for index, proposal in enumerate(proposals):
        agent_id = proposal.get('agentId')
        live_result = live_agent_responses.get(agent_id)
        if not isinstance(live_result, dict):
            continue

        live_found = True
        quantity = safe_int(proposal.get('metrics', {}).get('quantity'), 0)
        delivery_days = safe_int(round_summary.get('deliveryDays'), 0)
        price = safe_float(proposal.get('metrics', {}).get('price'), 0)
        margin = safe_float(proposal.get('metrics', {}).get('margin'), 0)

        if agent_id == 'finance':
            price = safe_float(live_result.get('final_price'), price)
            margin_value = safe_float(live_result.get('margin'), margin)
            margin = margin_value * 100 if margin_value <= 1 else margin_value
        elif agent_id == 'sales':
            price = safe_float(live_result.get('agreed_price'), price)
        elif agent_id == 'production':
            delivery_days = safe_int(live_result.get('production_days'), delivery_days)
        elif agent_id == 'logistics':
            parsed_days = extract_delivery_days_from_process_response(
                {'delivery_date': live_result.get('delivery_date')}
            )
            if parsed_days is not None:
                delivery_days = parsed_days

        proposal_view = _build_round_specific_proposal(
            agent_id=agent_id,
            live_result=live_result,
            round_number=round_number,
            order=round_summary.get('order_context') or {},
            quantity=quantity,
            price=price,
            delivery_days=delivery_days,
            margin=margin,
            all_live_approved=all_live_approved,
        )

        proposals[index] = {
            'agentId': agent_id,
            'round': round_number,
            'status': proposal_view['status'],
            'reasoning': proposal_view['reasoning'],
            'metrics': proposal_view['metrics'],
            'approved': proposal_view['approved'],
            'actions': proposal_view['actions'],
            'live': True,
        }

    round_summary['proposals'] = proposals
    if live_found:
        finance_proposal = next((item for item in proposals if item.get('agentId') == 'finance'), None)
        sales_proposal = next((item for item in proposals if item.get('agentId') == 'sales'), None)
        production_proposal = next((item for item in proposals if item.get('agentId') == 'production'), None)
        logistics_proposal = next((item for item in proposals if item.get('agentId') == 'logistics'), None)

        if finance_proposal:
            round_summary['margin'] = safe_float(finance_proposal.get('metrics', {}).get('margin'), round_summary.get('margin'))
            round_summary['price'] = safe_float(finance_proposal.get('metrics', {}).get('price'), round_summary.get('price'))
        if sales_proposal:
            round_summary['price'] = safe_float(sales_proposal.get('metrics', {}).get('price'), round_summary.get('price'))
        if production_proposal:
            round_summary['deliveryDays'] = safe_int(production_proposal.get('metrics', {}).get('deliveryDays'), round_summary.get('deliveryDays'))
        if logistics_proposal:
            round_summary['deliveryDays'] = max(
                safe_int(round_summary.get('deliveryDays'), 0),
                safe_int(logistics_proposal.get('metrics', {}).get('deliveryDays'), 0),
            )

        round_summary['shippingMode'] = 'ground' if all_live_approved else ('express' if round_number == 2 else 'air')
        round_summary['overtimeHours'] = 6 if all_live_approved else (10 if round_number == 2 else 12)
        round_summary['converged'] = bool(process_response.get('consensus_reached', all_live_approved))

    return round_summary


def build_actual_round_summary(order, round_number, process_response, previous_round=None):
    round_summary = build_round_summary(order, round_number, previous_round)
    round_summary = apply_live_agent_results_to_round(round_summary, process_response)
    return round_summary


def derive_revised_order(previous_order, process_response, round_number):
    revised_order = dict(previous_order)
    previous_context = dict(previous_order.get('negotiationContext') or {})
    original_price = safe_float(previous_context.get('original_requested_price'), safe_float(previous_order.get('requestedPrice'), 10.0))
    original_days = safe_int(
        previous_context.get('original_requested_delivery_days'),
        safe_int(previous_order.get('requestedDeliveryDays'), 18),
    )
    original_quantity = safe_int(previous_context.get('original_quantity'), safe_int(previous_order.get('quantity'), 1))
    blockers = get_blocking_agents(process_response)

    agent_responses = (process_response or {}).get('agent_responses') or {}
    procurement_result = agent_responses.get('procurement') or {}
    production_result = agent_responses.get('production') or {}
    logistics_result = agent_responses.get('logistics') or {}
    finance_result = agent_responses.get('finance') or {}
    sales_result = agent_responses.get('sales') or {}

    production_days = safe_int(production_result.get('production_days'), safe_int(previous_order.get('requestedDeliveryDays'), original_days))
    logistics_days = extract_delivery_days_from_process_response({'delivery_date': logistics_result.get('delivery_date')})
    if logistics_days is None:
        logistics_days = max(1, production_days + 2)

    finance_floor = safe_float(finance_result.get('final_price'), safe_float(previous_order.get('requestedPrice'), original_price))
    requested_price = safe_float(previous_order.get('requestedPrice'), original_price)
    requested_days = safe_int(previous_order.get('requestedDeliveryDays'), original_days)
    requested_quantity = safe_int(previous_order.get('quantity'), original_quantity)
    feasible_quantity = max(0, _procurement_feasible_quantity(previous_order, procurement_result))

    customer_profile = state.inventory_manager.get_customer_profile(previous_order.get('customer', '')) if state.inventory_manager else {}
    max_price_uplift = float(customer_profile.get('max_price_uplift', 0.20))
    delivery_buffer = int(customer_profile.get('acceptable_delivery_buffer_days', 2))
    max_customer_price = round(original_price * (1 + max_price_uplift), 2)
    primary_lead_with_buffer = int(state.inventory_manager.procurement_policy.get('primary_lead_time_days', 10)) + 2 if state.inventory_manager else 12

    target_price = requested_price
    target_days = max(requested_days, production_days, logistics_days)
    target_quantity = requested_quantity
    priority = revised_order.get('priority', 'rush')
    production_strategy = 'baseline'
    strategy_notes = []
    round_goal = 'Resolve blockers while preserving full order value.'
    revenue_goal = 'Protect margin while improving the customer offer.'
    revenue_goal_mode = 'baseline'

    if round_number == 2:
        if 'procurement' in blockers:
            target_days = max(target_days, primary_lead_with_buffer)
            strategy_notes.append(
                'Procurement is asked to source missing material externally instead of limiting the decision to current stock.'
            )
        if 'production' in blockers or 'logistics' in blockers:
            production_strategy = 'preempt_and_overtime'
            priority = 'critical'
            target_days = max(original_days, min(target_days, max(production_days, logistics_days)))
            target_price = max(target_price, finance_floor * 1.05, original_price * 1.08)
            revenue_goal = 'Use expedited premium to offset preemption and overtime while keeping the full order.'
            revenue_goal_mode = 'premium_recovery'
            strategy_notes.append(
                'Production is asked to evaluate stopping lower-priority work, reallocating slots, and running overtime for this order.'
            )
        if 'finance' in blockers:
            target_price = max(target_price, finance_floor, original_price * 1.05)
            revenue_goal_mode = revenue_goal_mode if revenue_goal_mode != 'baseline' else 'floor_recovery'
            strategy_notes.append('Finance is asked to recover the margin floor through a revised counter-offer.')
        if 'sales' in blockers:
            target_price = min(max(target_price, finance_floor), max_customer_price)
            target_days = max(target_days, original_days + delivery_buffer)
            strategy_notes.append('Sales is asked to test a premium-but-defensible offer against customer tolerance.')
        if not strategy_notes:
            strategy_notes.append('Round 2 keeps the order intact and validates whether a premium rush plan is acceptable.')
    else:
        round_goal = 'Present the final viable offer with explicit revenue protection.'
        revenue_goal = 'Maximize contribution margin on the final feasible deal.'
        revenue_goal_mode = 'margin_expansion'
        production_strategy = 'phased_split_delivery'
        priority = 'critical'
        target_days = max(target_days, original_days + max(3, delivery_buffer + 1), production_days + 2)
        target_price = max(target_price, finance_floor * 1.08, original_price * 1.10)
        strategy_notes.append('Final round asks operations to lock committed capacity and protect the account margin.')

        if 'procurement' in blockers and feasible_quantity > 0:
            target_quantity = min(requested_quantity, feasible_quantity)
            if target_quantity < requested_quantity:
                strategy_notes.append(
                    f'Immediate allocation is reduced to {target_quantity} units to avoid a full rejection while supply is replenished.'
                )
        if 'production' in blockers:
            target_days = max(target_days, production_days + 3)
            strategy_notes.append('Production is asked for a phased delivery schedule instead of a single completion date.')
        if 'sales' in blockers:
            target_price = min(target_price, max_customer_price)
            target_days = max(target_days, original_days + delivery_buffer + 1)
            strategy_notes.append('Price is capped at customer tolerance; any further improvement must come from schedule, not discounting.')
        if not strategy_notes:
            strategy_notes.append('Final round converts aligned agent positions into a firm customer-ready proposal.')

    revised_order['quantity'] = max(1, target_quantity)
    revised_order['requestedPrice'] = round(target_price, 2)
    revised_order['requestedDeliveryDays'] = int(target_days)
    revised_order['priority'] = priority
    revised_order['customerLocation'] = previous_order.get('customerLocation')
    revised_order['negotiationContext'] = {
        **previous_context,
        'original_requested_price': original_price,
        'original_requested_delivery_days': original_days,
        'original_quantity': original_quantity,
        'round_number': round_number,
        'round_goal': round_goal,
        'revenue_goal': revenue_goal,
        'revenue_goal_mode': revenue_goal_mode,
        'production_strategy': production_strategy,
        'blocking_agents': blockers,
        'strategy_notes': strategy_notes,
        'previous_rejection_reason': (process_response or {}).get('message'),
        'customer_price_ceiling': max_customer_price,
    }
    return revised_order


def extract_delivery_days_from_process_response(process_response):
    delivery_date = process_response.get('delivery_date')
    if not delivery_date:
        return None
    try:
        delivery_dt = datetime.strptime(delivery_date, '%Y-%m-%d').date()
        today = datetime.utcnow().date()
        return min(60, max(1, (delivery_dt - today).days))
    except ValueError:
        return None


def synthesize_consensus(order, rounds, process_response=None):
    final_round = rounds[-1]
    approved = bool(final_round.get('converged'))
    final_price = safe_float(final_round.get('price'), 10.8)
    final_delivery_days = safe_int(final_round.get('deliveryDays'), 19)
    final_margin = safe_float(final_round.get('margin'), 20.6)
    shipping_mode = final_round.get('shippingMode', 'ground')
    overtime_hours = safe_int(final_round.get('overtimeHours'), 8)
    confidence = 94 if approved else 62
    rejection_reason = None

    if process_response:
        approved = bool(process_response.get('consensus_reached', approved))
        final_price = safe_float(process_response.get('final_price'), final_price)
        profit_margin = process_response.get('cost_breakdown', {}).get('profit_margin')
        final_margin = round(safe_float(profit_margin, 0.25) * 100, 1)
        inferred_days = extract_delivery_days_from_process_response(process_response)
        if inferred_days is not None:
            final_delivery_days = inferred_days
        confidence = 90 if approved else 58
        if not approved:
            rejection_reason = (
                process_response.get('message')
                or (process_response.get('agent_responses', {}).get('procurement', {}) or {}).get('reasoning')
            )

    risk_score = 'Low' if final_margin >= 20 else ('Medium' if final_margin >= 15 else 'High')
    order_id = order.get('id', 'ORD-RUSH-001')
    quantity = safe_int(order.get('quantity'), 5000)
    product = order.get('product', 'PMP-STD-100')

    if approved:
        summary = (
            f'Order {order_id} APPROVED. {quantity} units of {product} at '
            f'${final_price:.2f}/unit, delivered in {final_delivery_days} days via '
            f'{shipping_mode} freight. Margin: {final_margin:.1f}%. '
            f'All agents reached consensus in {len(rounds)} rounds.'
        )
    else:
        if rejection_reason:
            summary = (
                f'Order {order_id} REJECTED. Reason: {rejection_reason} '
                f'(after {len(rounds)} rounds).'
            )
        else:
            summary = (
                f'Order {order_id} REJECTED. Unable to meet requested terms within '
                f'operational constraints after {len(rounds)} rounds.'
            )

    return {
        'approved': approved,
        'finalPrice': round(final_price, 2),
        'finalDeliveryDays': final_delivery_days,
        'finalMargin': round(final_margin, 1),
        'shippingMode': shipping_mode,
        'riskScore': risk_score,
        'confidence': confidence,
        'supplier': BASELINE['primarySupplier'],
        'overtimeHours': overtime_hours,
        'rejectionReason': rejection_reason,
        'summary': summary,
    }


def sse_event(event_type, data):
    return f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"


def build_round_messages(round_number, id_counter, round_summary=None):
    if not round_summary or not round_summary.get('proposals'):
        return [], id_counter

    blockers = [proposal for proposal in round_summary.get('proposals', []) if not proposal.get('approved')]
    strategy = round_summary.get('strategy') or {}
    strategy_goal = strategy.get('goal')
    if round_number == 1:
        directive = 'Broadcasting order to all agents. Complete initial feasibility checks.'
    elif strategy_goal:
        directive = strategy_goal
    elif blockers:
        directive = 'Blocking agents must counter with feasible terms. Supporting agents validate revised options.'
    else:
        directive = 'All agents are aligned. Finalize consensus and customer-ready terms.'

    messages = []
    timestamp = int(time.time() * 1000)

    id_counter += 1
    messages.append({
        'id': f'msg-{id_counter}',
        'from': 'orchestrator',
        'to': 'all',
        'round': round_number,
        'type': 'directive',
        'message': directive,
        'timestamp': timestamp + id_counter,
    })

    for proposal in round_summary.get('proposals', []):
        id_counter += 1
        message_type = 'agreement' if proposal.get('approved') and proposal.get('status') == 'agreed' else ('objection' if not proposal.get('approved') else 'proposal')
        messages.append({
            'id': f'msg-{id_counter}',
            'from': proposal.get('agentId'),
            'to': 'orchestrator',
            'round': round_number,
            'type': message_type,
            'message': _short_reason(proposal.get('reasoning'), 'Position updated.'),
            'timestamp': timestamp + id_counter,
        })

    return messages, id_counter


def get_agent_processing_delay(agent_id, round_number):
    """
    Return per-agent completion offset (seconds) for SSE simulation.
    Each value represents when that agent should finish relative to round start.
    """
    base_completion_offset = {
        'logistics': 2.0,
        'sales': 4.0,
        'production': 6.0,
        'procurement': 8.0,
        'finance': 10.0,
    }.get(agent_id, 5.0)

    # Slightly longer rounds as negotiation deepens.
    round_bump = 0.75 * max(0, round_number - 1)
    return base_completion_offset + round_bump
