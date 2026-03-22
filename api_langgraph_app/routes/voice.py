import os

from flask import Blueprint, jsonify, request

from .. import state
from outbound_call_agent import (
    DEFAULT_CUSTOMER_NUMBER,
    fetch_latest_transcript_fallback,
    get_voice_agent_state,
    maybe_fetch_latest_transcript_fallback,
    reset_voice_agent_state,
    set_callback_number_override,
    set_last_call_result,
    store_voice_agent_payload,
    trigger_decision_callback,
    trigger_call,
)


voice_bp = Blueprint('voice_api', __name__, url_prefix='/api')


@voice_bp.post('/voice-agent/start')
@voice_bp.post('/call')
def start_voice_agent():
    body = request.get_json(silent=True) or {}
    debug_tag = body.get('debugTag') or body.get('debug_tag') or os.getenv('VOICE_AGENT_DEBUG_MODE')
    replay_call_id = body.get('callId') or body.get('call_id') or os.getenv('VOICE_AGENT_DEBUG_CALL_ID')
    body_customer_number = body.get('customer_number') or body.get('customerNumber')
    debug_customer_number = body_customer_number or os.getenv('VOICE_AGENT_DEBUG_CUSTOMER_NUMBER')
    customer_number = (
        debug_customer_number if debug_tag == 'transcript-replay' and debug_customer_number
        else body_customer_number or DEFAULT_CUSTOMER_NUMBER
    )
    state.logger.info(
        '/api/voice-agent/start requested for customerNumber=%s debugTag=%s callId=%s bodyKeys=%s',
        customer_number,
        debug_tag,
        replay_call_id,
        sorted(body.keys()),
    )

    try:
        reset_voice_agent_state()
        set_callback_number_override(customer_number)
        if debug_tag == 'transcript-replay':
            result = fetch_latest_transcript_fallback(call_id=replay_call_id)
            current_state = get_voice_agent_state()
            state.logger.info(
                '/api/voice-agent/start transcript-replay success callId=%s ready=%s missing=%s',
                result.get('callId'),
                current_state.get('ready'),
                current_state.get('missingFields'),
            )
            return jsonify(
                {
                    'status': 'SUCCESS',
                    'message': 'Transcript replay loaded. Intake call bypassed.',
                    'customerNumber': customer_number,
                    'debugTag': debug_tag,
                    'call': result.get('call'),
                    'voiceResult': current_state,
                }
            )

        call_result = trigger_call(customer_number)
        set_last_call_result(call_result)
        state.logger.info('/api/voice-agent/start success customerNumber=%s callResult=%s', customer_number, str(call_result)[:1000])
        return jsonify(
            {
                'status': 'SUCCESS',
                'message': 'Outbound voice call triggered.',
                'customerNumber': customer_number,
                'call': call_result,
                'voiceResult': get_voice_agent_state(),
            }
        )
    except Exception as exc:
        state.logger.error('/api/voice-agent/start failed for customerNumber=%s error=%s', customer_number, str(exc))
        return (
            jsonify(
                {
                    'status': 'FAILURE',
                    'message': str(exc),
                    'customerNumber': customer_number,
                }
            ),
            500,
        )


@voice_bp.post('/voice-agent/webhook')
@voice_bp.post('/voice-agent/result')
def receive_voice_agent_result():
    body = request.get_json(silent=True)
    if body is None:
        state.logger.warning('/api/voice-agent/webhook received non-JSON payload')
        return jsonify({'status': 'FAILURE', 'message': 'Expected JSON payload.'}), 400

    state.logger.info('/api/voice-agent/webhook received keys=%s payload=%s', sorted(body.keys()) if isinstance(body, dict) else [], str(body)[:1500])
    voice_state = store_voice_agent_payload(body)
    state.logger.info('/api/voice-agent/webhook normalized ready=%s missing=%s order=%s', voice_state.get('ready'), voice_state.get('missingFields'), voice_state.get('order'))
    return jsonify(
        {
            'status': 'SUCCESS',
            'message': 'Voice agent payload processed.',
            'voiceResult': voice_state,
        }
    )


@voice_bp.get('/voice-agent/latest')
def latest_voice_agent_result():
    fallback_used = False
    fallback_result = maybe_fetch_latest_transcript_fallback(force=False)
    if fallback_result is not None:
        fallback_used = True
    current_state = get_voice_agent_state()
    state.logger.info(
        '/api/voice-agent/latest ready=%s missing=%s lastPayloadKeys=%s fallbackUsed=%s fallbackStatus=%s',
        current_state.get('ready'),
        current_state.get('missingFields'),
        current_state.get('lastPayloadKeys'),
        fallback_used,
        current_state.get('lastFallbackStatus'),
    )
    return jsonify(
        {
            'status': 'SUCCESS',
            'voiceResult': current_state,
            'fallbackUsed': fallback_used,
        }
    )


@voice_bp.get('/voice-agent/latest-transcript')
@voice_bp.get('/latest_transcript')
def latest_transcript():
    call_id = request.args.get('callId')
    state.logger.info('/api/voice-agent/latest-transcript requested callId=%s', call_id)
    try:
        result = fetch_latest_transcript_fallback(call_id=call_id)
        return jsonify(
            {
                'status': 'SUCCESS',
                'message': 'Fetched fallback transcript from Vapi call record.',
                **result,
            }
        )
    except Exception as exc:
        state.logger.error('/api/voice-agent/latest-transcript failed callId=%s error=%s', call_id, str(exc))
        return (
            jsonify(
                {
                    'status': 'FAILURE',
                    'message': str(exc),
                    'callId': call_id,
                }
            ),
            500,
        )


@voice_bp.post('/voice-agent/callback')
def start_decision_callback():
    body = request.get_json(silent=True) or {}
    consensus = body.get('consensus') or {}
    order = body.get('order') or {}
    customer_number = body.get('customer_number') or body.get('customerNumber')
    state.logger.info(
        '/api/voice-agent/callback requested customerNumber=%s approved=%s orderId=%s',
        customer_number,
        consensus.get('approved'),
        order.get('id'),
    )

    if not isinstance(consensus, dict) or not isinstance(order, dict):
        return jsonify({'status': 'FAILURE', 'message': 'Expected object payload for order and consensus.'}), 400

    try:
        callback_call = trigger_decision_callback(order, consensus, customer_number=customer_number)
        return jsonify(
            {
                'status': 'SUCCESS',
                'message': 'Decision callback triggered.',
                'call': callback_call,
                'voiceResult': get_voice_agent_state(),
            }
        )
    except Exception as exc:
        state.logger.error('/api/voice-agent/callback failed error=%s', str(exc))
        return (
            jsonify(
                {
                    'status': 'FAILURE',
                    'message': str(exc),
                }
            ),
            500,
        )
