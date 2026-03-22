from flask import Blueprint, jsonify, request

from ..agents import (
    AGENT_CONFIGS,
    AGENT_IDS,
    get_agent_description,
    get_agent_tools,
    get_operational_parameters,
)
from ..constants import BASELINE
from ..services import (
    mock_agent_proposal,
    safe_int,
)


agents_bp = Blueprint('agents_api', __name__, url_prefix='/api')


@agents_bp.get('/agents')
def list_agents():
    agents = []
    for agent in AGENT_CONFIGS:
        agents.append({
            'id': agent['id'],
            'name': agent['name'],
            'role': agent['role'],
            'color': agent['color'],
            'avatar': f"/agents/{agent['id']}.jpg",
            'tools': get_agent_tools(agent['id']),
            'description': get_agent_description(agent['id']),
        })
    return jsonify({'agents': agents})


@agents_bp.get('/agents/<agent_id>')
def get_agent(agent_id):
    config = next((a for a in AGENT_CONFIGS if a['id'] == agent_id), None)
    if config is None:
        return jsonify({'error': f"Agent '{agent_id}' not found"}), 404

    return jsonify({
        'id': config['id'],
        'name': config['name'],
        'role': config['role'],
        'color': config['color'],
        'avatar': f"/agents/{config['id']}.jpg",
        'operationalParameters': get_operational_parameters(config['id']),
    })


@agents_bp.post('/agents/<agent_id>/analyze')
def analyze_agent(agent_id):
    if agent_id not in AGENT_IDS:
        return jsonify({'error': f'Invalid agent: {agent_id}'}), 400

    body = request.get_json(silent=True) or {}
    if 'order' not in body:
        return jsonify({'error': "Missing 'order' in request body"}), 400

    order = body['order']
    round_number = safe_int(body.get('round'), 1)
    previous_round = body.get('previousRound')
    proposal = mock_agent_proposal(agent_id, order, round_number, previous_round)
    return jsonify({
        'agentId': agent_id,
        'round': round_number,
        'proposal': proposal,
    })


@agents_bp.get('/baseline')
def baseline():
    return jsonify({
        'production': {
            'capacityPerWeek': BASELINE['productionCapacity'],
            'standardLeadTimeDays': BASELINE['standardLeadTimeDays'],
            'overtimeCostPerHour': BASELINE['overtimeCostPerHour'],
            'maxOvertimeHoursPerDay': BASELINE['maxOvertimeHoursPerDay'],
            'workingDaysPerWeek': BASELINE['workingDaysPerWeek'],
        },
        'finance': {
            'baseCostPerUnit': BASELINE['baseCostPerUnit'],
            'marginFloor': BASELINE['marginFloor'],
            'targetMargin': BASELINE['targetMargin'],
            'rushSurchargeRate': BASELINE['rushSurchargeRate'],
        },
        'logistics': {
            'shippingModes': {
                'ground': {'costPerUnit': BASELINE['groundCostPerUnit'], 'transitDays': BASELINE['groundShippingDays']},
                'express': {'costPerUnit': BASELINE['expressCostPerUnit'], 'transitDays': BASELINE['expressShippingDays']},
                'air': {'costPerUnit': BASELINE['airCostPerUnit'], 'transitDays': BASELINE['airShippingDays']},
            },
        },
        'procurement': {
            'primary': {
                'supplier': BASELINE['primarySupplier'],
                'leadTimeDays': BASELINE['primaryLeadTimeDays'],
                'costPerUnit': BASELINE['materialCostPerUnit'],
            },
            'alternate': {
                'supplier': BASELINE['alternateSupplier'],
                'leadTimeDays': BASELINE['alternateLeadTimeDays'],
                'costPerUnit': BASELINE['alternateMaterialCostPerUnit'],
            },
        },
        'sales': {
            'customerTier': BASELINE['customerTier'],
            'relationshipYears': BASELINE['relationshipYears'],
            'annualVolume': BASELINE['annualVolume'],
            'acceptableDeliveryBuffer': BASELINE['acceptableDeliveryBuffer'],
        },
    })
