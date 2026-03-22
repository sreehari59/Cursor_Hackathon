import io
import logging
import os
import re
import threading
import time
import wave
import json
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from vapi import Vapi

try:
    import websocket
except ImportError:  # pragma: no cover - dependency may not be installed yet
    websocket = None


load_dotenv()

logger = logging.getLogger(__name__)

VAPI_API_KEY = os.environ.get('VAPI_API_KEY')
ASSISTANT_ID = os.environ.get('ASSISTANT_ID')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
DEFAULT_CUSTOMER_NUMBER = os.environ.get('DEFAULT_CUSTOMER_NUMBER', '+918547476466')


BASE_URL = 'https://api.vapi.ai'
REQUIRED_ORDER_FIELDS = ['product', 'quantity', 'requestedPrice', 'requestedDeliveryDays']
TRANSCRIBE_MODEL = os.environ.get('VOICE_TRANSCRIBE_MODEL', 'gpt-4o-mini-transcribe')
TRANSCRIBE_CHUNK_SECONDS = int(os.environ.get('VOICE_TRANSCRIBE_CHUNK_SECONDS', '6'))
VOICE_STRUCTURED_MODEL = os.environ.get('VOICE_STRUCTURED_MODEL', 'gpt-4o-mini')
DEFAULT_PCM_SAMPLE_RATE = int(os.environ.get('VOICE_PCM_SAMPLE_RATE', '16000'))
DEFAULT_MULAW_SAMPLE_RATE = int(os.environ.get('VOICE_MULAW_SAMPLE_RATE', '8000'))
FORCE_MONITOR_AUDIO_FORMAT = os.environ.get('VOICE_MONITOR_AUDIO_FORMAT')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') or os.environ.get('OPEN_AI_API_KEY')
_MATERIALS_PATH = Path(__file__).resolve().parent / 'data' / 'materials.json'
try:
    _SKU_ROWS = json.loads(_MATERIALS_PATH.read_text(encoding='utf-8'))
except Exception:
    _SKU_ROWS = []
KNOWN_SKUS = [str(row.get('sku')) for row in _SKU_ROWS if isinstance(row, dict) and row.get('sku')]

_voice_agent_state = {
    'ready': False,
    'order': None,
    'missingFields': list(REQUIRED_ORDER_FIELDS),
    'lastCall': None,
    'lastCallId': None,
    'lastPayloadKeys': [],
    'lastPayloadPreview': None,
    'transcriptText': '',
    'transcriptSegments': [],
    'monitorStatus': 'idle',
    'audioBytesReceived': 0,
    'audioFormat': None,
    'sampleRate': None,
    'monitorErrors': [],
    'lastFallbackAt': None,
    'lastFallbackStatus': None,
    'lastDecisionCall': None,
    'lastDecisionCallTarget': None,
    'callbackNumberOverride': None,
    'updatedAt': None,
}

_state_lock = threading.RLock()
_active_monitor: dict[str, Any] = {'thread': None, 'stop_event': None, 'call_id': None}
_openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_vapi_client = Vapi(token=VAPI_API_KEY) if VAPI_API_KEY else None
_assistant_cache: dict[str, Any] = {}


class VoiceOrderStructuredOutput(BaseModel):
    customer: str | None = Field(default=None)
    product: str | None = Field(default=None)
    quantity: int | None = Field(default=None)
    requestedPrice: float | None = Field(default=None)
    requestedDeliveryDays: int | None = Field(default=None)
    priority: str | None = Field(default=None)


def trigger_call(customer_number: str | None = None) -> dict[str, Any]:
    if not VAPI_API_KEY or not ASSISTANT_ID or not PHONE_NUMBER_ID:
        raise RuntimeError('Missing VAPI_API_KEY, ASSISTANT_ID, or PHONE_NUMBER_ID.')

    target_number = customer_number or DEFAULT_CUSTOMER_NUMBER
    payload = {
        'assistantId': ASSISTANT_ID,
        'phoneNumberId': PHONE_NUMBER_ID,
        'customer': {
            'number': target_number,
        },
    }

    return _create_vapi_call(payload, target_number, call_kind='intake')


def trigger_decision_callback(
    order: dict[str, Any],
    consensus: dict[str, Any],
    customer_number: str | None = None,
) -> dict[str, Any]:
    if not VAPI_API_KEY or not ASSISTANT_ID or not PHONE_NUMBER_ID:
        raise RuntimeError('Missing VAPI_API_KEY, ASSISTANT_ID, or PHONE_NUMBER_ID.')

    target_number = resolve_callback_customer_number(customer_number)
    first_message, system_prompt = build_decision_callback_script(order, consensus)
    callback_assistant = build_callback_assistant(first_message, system_prompt)
    payload = {
        'assistant': callback_assistant,
        'phoneNumberId': PHONE_NUMBER_ID,
        'customer': {
            'number': target_number,
        },
        'metadata': {
            'flow': 'decision-callback',
            'orderId': order.get('id'),
            'approved': bool(consensus.get('approved')),
        },
    }
    result = _create_vapi_call(payload, target_number, call_kind='decision-callback')
    with _state_lock:
        _voice_agent_state['lastDecisionCall'] = result
        _voice_agent_state['lastDecisionCallTarget'] = target_number
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)
    return result


def resolve_callback_customer_number(customer_number: str | None = None) -> str:
    if customer_number:
        return str(customer_number)
    current_state = get_voice_agent_state()
    override = current_state.get('callbackNumberOverride')
    if override:
        return str(override)
    last_call = current_state.get('lastCall') or {}
    customer = last_call.get('customer') or {}
    number = customer.get('number')
    if number:
        return str(number)
    return DEFAULT_CUSTOMER_NUMBER


def build_decision_callback_script(order: dict[str, Any], consensus: dict[str, Any]) -> tuple[str, str]:
    customer = str(order.get('customer') or 'customer')
    order_id = str(order.get('id') or 'the order')
    product = str(order.get('product') or 'the requested product')
    quantity = _safe_int(order.get('quantity'), 0) or 0
    approved = bool(consensus.get('approved'))

    if approved:
        final_price = _safe_float(consensus.get('finalPrice'), 0.0) or 0.0
        final_days = _safe_int(consensus.get('finalDeliveryDays'), 0) or 0
        first_message = (
            f'Hello {customer}, this is Sagar from Aqua Pumps private limited with an update on order {order_id}. '
            f'Your order for {quantity} units of {product} is approved at ${final_price:.2f} per unit '
            f'with delivery in {final_days} days.'
        )
        system_prompt = (
            'You are a SYNK callback agent. '
            'Deliver the approved order outcome clearly and concisely. '
            'Confirm only these facts: order is approved, product, quantity, final price, and final delivery days. '
            'If the customer asks for anything beyond these facts, say a team member will follow up shortly. '
            'Keep the call brief and professional.'
        )
    else:
        rejection_reason = str(consensus.get('rejectionReason') or consensus.get('summary') or 'we could not approve the requested terms').strip()
        first_message = (
            f'Hello {customer}, this is Sagar from Aqua Pumps private limited with an update on order {order_id}. '
            f'We could not approve the request for {quantity} units of {product} under the submitted terms. '
            f'The main reason is: {rejection_reason}.'
        )
        system_prompt = (
            'You are a SYNK callback agent. '
            'Deliver the rejected order outcome clearly and concisely. '
            'Confirm only these facts: order is not approved, product, quantity, and the stated rejection reason. '
            'If asked for alternatives, say revised options will follow shortly from the team. '
            'Keep the call brief and professional.'
        )

    return first_message, system_prompt


def build_callback_assistant(first_message: str, system_prompt: str) -> dict[str, Any]:
    base_assistant = get_assistant_details(ASSISTANT_ID)
    base_model = base_assistant.get('model') if isinstance(base_assistant, dict) else {}
    model_payload = {
        'provider': (base_model or {}).get('provider', 'openai'),
        'model': (base_model or {}).get('model', VOICE_STRUCTURED_MODEL),
        'messages': [{'role': 'system', 'content': system_prompt}],
    }
    if isinstance(base_model, dict):
        for key in ['temperature', 'maxTokens', 'topP', 'presencePenalty', 'frequencyPenalty']:
            if key in base_model and base_model.get(key) is not None:
                model_payload[key] = base_model.get(key)

    assistant_payload = {
        'name': 'SYNK Decision Callback',
        'firstMessage': first_message,
        'firstMessageMode': 'assistant-speaks-first',
        'model': model_payload,
    }

    if isinstance(base_assistant, dict):
        for field in ['voice', 'transcriber', 'backgroundSound', 'silenceTimeoutSeconds', 'maxDurationSeconds']:
            value = base_assistant.get(field)
            if value is not None:
                assistant_payload[field] = value

    return assistant_payload


def _create_vapi_call(payload: dict[str, Any], target_number: str, call_kind: str) -> dict[str, Any]:
    headers = {
        'Authorization': f'Bearer {VAPI_API_KEY}',
        'Content-Type': 'application/json',
    }

    logger.info(
        'Triggering %s Vapi call to %s using phoneNumberId=%s payloadKeys=%s',
        call_kind,
        target_number,
        PHONE_NUMBER_ID,
        sorted(payload.keys()),
    )
    try:
        response = requests.post(
            f'{BASE_URL}/call',
            json=payload,
            headers=headers,
            timeout=15,
        )
        logger.info('Vapi /call response status=%s for %s', response.status_code, call_kind)
        response.raise_for_status()
        response_json = response.json()
        logger.info('Vapi /call response body for %s=%s', call_kind, _truncate_for_log(response_json))
        return response_json
    except requests.exceptions.RequestException as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
        response_text = getattr(getattr(exc, 'response', None), 'text', '')
        logger.error(
            'Vapi /call request failed for %s. status=%s error=%s response=%s',
            call_kind,
            status_code,
            str(exc),
            _truncate_for_log(response_text),
        )
        raise


def get_assistant_details(assistant_id: str) -> dict[str, Any]:
    cached = _assistant_cache.get(assistant_id)
    if isinstance(cached, dict):
        return cached
    response = _vapi_request('GET', f'/assistant/{assistant_id}')
    if not isinstance(response, dict):
        raise RuntimeError(f'Unexpected Vapi assistant response for {assistant_id}: {type(response)}')
    _assistant_cache[assistant_id] = response
    return response


def reset_voice_agent_state() -> dict[str, Any]:
    _stop_active_monitor()
    with _state_lock:
        _voice_agent_state.update(
            {
                'ready': False,
                'order': None,
                'missingFields': list(REQUIRED_ORDER_FIELDS),
                'lastCall': None,
                'lastCallId': None,
                'lastPayloadKeys': [],
                'lastPayloadPreview': None,
                'transcriptText': '',
                'transcriptSegments': [],
                'monitorStatus': 'idle',
                'audioBytesReceived': 0,
                'audioFormat': None,
                'sampleRate': None,
                'monitorErrors': [],
                'lastFallbackAt': None,
                'lastFallbackStatus': None,
                'lastDecisionCall': None,
                'lastDecisionCallTarget': None,
                'callbackNumberOverride': None,
                'updatedAt': int(time.time() * 1000),
            }
        )
    return get_voice_agent_state()


def set_last_call_result(result: dict[str, Any]) -> None:
    with _state_lock:
        _voice_agent_state['lastCall'] = result
        _voice_agent_state['lastCallId'] = result.get('id')
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)
    logger.info('Stored last outbound call result=%s', _truncate_for_log(result))
    _start_active_monitor(result)


def set_callback_number_override(customer_number: str | None) -> None:
    normalized = str(customer_number).strip() if customer_number else None
    with _state_lock:
        _voice_agent_state['callbackNumberOverride'] = normalized or None
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)
    logger.info('Stored callback number override=%s', normalized)


def store_voice_agent_payload(payload: Any) -> dict[str, Any]:
    normalized_order = extract_submission_order(payload)
    missing_fields = [
        field
        for field in REQUIRED_ORDER_FIELDS
        if normalized_order.get(field) in [None, '', 0]
    ]

    with _state_lock:
        _voice_agent_state.update(
            {
                'ready': len(missing_fields) == 0,
                'order': normalized_order if len(missing_fields) == 0 else None,
                'missingFields': missing_fields,
                'lastPayloadKeys': _payload_keys(payload),
                'lastPayloadPreview': _payload_preview(payload),
                'updatedAt': int(time.time() * 1000),
            }
        )
    logger.info(
        'Voice agent payload stored. ready=%s missing=%s keys=%s normalized_order=%s payload_preview=%s',
        _voice_agent_state['ready'],
        missing_fields,
        _voice_agent_state['lastPayloadKeys'],
        normalized_order,
        _truncate_for_log(_voice_agent_state['lastPayloadPreview']),
    )
    return get_voice_agent_state()


def get_voice_agent_state() -> dict[str, Any]:
    with _state_lock:
        return {
            'ready': bool(_voice_agent_state.get('ready')),
            'order': _voice_agent_state.get('order'),
            'missingFields': list(_voice_agent_state.get('missingFields') or []),
            'lastCall': _voice_agent_state.get('lastCall'),
            'lastCallId': _voice_agent_state.get('lastCallId'),
            'lastPayloadKeys': list(_voice_agent_state.get('lastPayloadKeys') or []),
            'lastPayloadPreview': _voice_agent_state.get('lastPayloadPreview'),
            'transcriptText': _voice_agent_state.get('transcriptText', ''),
            'transcriptSegments': list(_voice_agent_state.get('transcriptSegments') or []),
            'monitorStatus': _voice_agent_state.get('monitorStatus'),
            'audioBytesReceived': _voice_agent_state.get('audioBytesReceived', 0),
            'audioFormat': _voice_agent_state.get('audioFormat'),
            'sampleRate': _voice_agent_state.get('sampleRate'),
            'monitorErrors': list(_voice_agent_state.get('monitorErrors') or []),
            'lastFallbackAt': _voice_agent_state.get('lastFallbackAt'),
            'lastFallbackStatus': _voice_agent_state.get('lastFallbackStatus'),
            'lastDecisionCall': _voice_agent_state.get('lastDecisionCall'),
            'lastDecisionCallTarget': _voice_agent_state.get('lastDecisionCallTarget'),
            'callbackNumberOverride': _voice_agent_state.get('callbackNumberOverride'),
            'updatedAt': _voice_agent_state.get('updatedAt'),
        }


def fetch_latest_transcript_fallback(call_id: str | None = None) -> dict[str, Any]:
    latest_call_id = call_id or get_voice_agent_state().get('lastCallId')
    if not latest_call_id:
        calls = list_recent_calls(limit=1)
        if not calls:
            raise RuntimeError('No calls found in this Vapi account.')
        latest_call_id = calls[0].get('id')

    call_data = get_call_details(str(latest_call_id))
    transcript_entries = extract_call_transcript_entries(call_data)
    transcript_text = _serialize_transcript_entries(transcript_entries)

    if transcript_entries:
        _merge_fallback_transcript(call_data, transcript_entries, transcript_text)
    with _state_lock:
        _voice_agent_state['lastFallbackAt'] = int(time.time() * 1000)
        _voice_agent_state['lastFallbackStatus'] = 'success' if transcript_entries else 'empty'
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)

    return {
        'callId': latest_call_id,
        'transcript': transcript_entries,
        'transcriptText': transcript_text,
        'voiceResult': get_voice_agent_state(),
        'call': {
            'id': call_data.get('id'),
            'status': call_data.get('status'),
            'endedReason': call_data.get('endedReason'),
            'endedMessage': call_data.get('endedMessage'),
            'startedAt': call_data.get('startedAt'),
            'endedAt': call_data.get('endedAt'),
        },
    }


def maybe_fetch_latest_transcript_fallback(force: bool = False, call_id: str | None = None) -> dict[str, Any] | None:
    current_state = get_voice_agent_state()
    if not force and current_state.get('ready'):
        return None

    now_ms = int(time.time() * 1000)
    last_fallback_at = current_state.get('lastFallbackAt') or 0
    fallback_interval_ms = int(os.environ.get('VOICE_FALLBACK_INTERVAL_MS', '10000'))
    if not force and now_ms - int(last_fallback_at) < fallback_interval_ms:
        return None

    try:
        result = fetch_latest_transcript_fallback(call_id=call_id)
        return result
    except Exception as exc:
        with _state_lock:
            _voice_agent_state['lastFallbackAt'] = now_ms
            _voice_agent_state['lastFallbackStatus'] = f'error: {str(exc)}'
            _voice_agent_state['updatedAt'] = now_ms
        logger.warning('Fallback transcript fetch failed: %s', str(exc))
        return None


def extract_submission_order(payload: Any) -> dict[str, Any]:
    candidates = _collect_candidate_dicts(payload)
    best_order = {}
    best_score = -1

    for candidate in candidates:
        order = _normalize_candidate(candidate)
        score = _candidate_score(order)
        if score > best_score:
            best_order = order
            best_score = score

    return {
        'id': best_order.get('id') or f'ORD-VOICE-{str(int(time.time() * 1000))[-6:]}',
        'customer': best_order.get('customer') or 'Voice Customer',
        'product': best_order.get('product'),
        'quantity': best_order.get('quantity'),
        'requestedPrice': best_order.get('requestedPrice'),
        'requestedDeliveryDays': best_order.get('requestedDeliveryDays'),
        'priority': best_order.get('priority') or 'rush',
    }


def _collect_candidate_dicts(payload: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            results.append(value)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return results


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    product = _first_value(candidate, ['product', 'product_sku', 'sku', 'item'])
    quantity = _safe_int(_first_value(candidate, ['quantity', 'qty', 'units']), None)
    requested_price = _safe_float(
        _first_value(candidate, ['requestedPrice', 'requested_price', 'target_price', 'price_per_unit', 'price']),
        None,
    )
    requested_days = _safe_int(
        _first_value(candidate, ['requestedDeliveryDays', 'requested_delivery_days', 'delivery_days', 'deliveryDays', 'days']),
        None,
    )
    customer = _first_value(candidate, ['customer', 'customer_name', 'company', 'customerName'])
    order_id = _first_value(candidate, ['id', 'order_id', 'orderId'])
    priority = _normalize_priority(_first_value(candidate, ['priority', 'urgency']))

    return {
        'id': order_id,
        'customer': customer,
        'product': product,
        'quantity': quantity,
        'requestedPrice': requested_price,
        'requestedDeliveryDays': requested_days,
        'priority': priority,
    }


def _candidate_score(order: dict[str, Any]) -> int:
    score = 0
    for field in REQUIRED_ORDER_FIELDS:
        if order.get(field) not in [None, '', 0]:
            score += 1
    if order.get('customer'):
        score += 1
    if order.get('id'):
        score += 1
    return score


def _first_value(candidate: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in candidate and candidate.get(key) not in [None, '']:
            return candidate.get(key)
    return None


def _normalize_priority(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {'rush', 'critical'}:
        return 'rush'
    if raw in {'standard', 'normal'}:
        return 'standard'
    return raw or None


def _safe_int(value: Any, default: int | None) -> int | None:
    try:
        if value is None:
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float | None) -> float | None:
    try:
        if value is None:
            return default
        return float(str(value).strip().replace('$', '').replace(',', ''))
    except (TypeError, ValueError):
        return default


def _payload_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())
    return []


def _payload_preview(payload: Any) -> Any:
    if isinstance(payload, dict):
        preview: dict[str, Any] = {}
        for key, value in list(payload.items())[:8]:
            if isinstance(value, dict):
                preview[str(key)] = {str(nested_key): value[nested_key] for nested_key in list(value.keys())[:8]}
            elif isinstance(value, list):
                preview[str(key)] = value[:3]
            else:
                preview[str(key)] = value
        return preview
    if isinstance(payload, list):
        return payload[:3]
    return payload


def _truncate_for_log(value: Any, limit: int = 1000) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + '...<truncated>'


def list_recent_calls(limit: int = 1) -> list[dict[str, Any]]:
    client = _get_vapi_client()
    response = client.calls.list(limit=limit)
    calls = [_sdk_to_dict(item) for item in list(response or [])]
    logger.info('Fetched %s recent Vapi calls through SDK.', len(calls))
    return calls


def get_call_details(call_id: str) -> dict[str, Any]:
    client = _get_vapi_client()
    response = client.calls.get(call_id)
    call_data = _sdk_to_dict(response)
    logger.info('Fetched Vapi call details for call_id=%s status=%s through SDK', call_id, call_data.get('status'))
    return call_data


def extract_call_transcript_entries(call_data: dict[str, Any]) -> list[dict[str, Any]]:
    top_level_transcript = call_data.get('transcript')
    if isinstance(top_level_transcript, str) and top_level_transcript.strip():
        entries = _parse_transcript_string(top_level_transcript)
        if entries:
            logger.info('Extracted %s transcript entries from call.transcript string', len(entries))
            return entries

    artifact = call_data.get('artifact') or {}
    transcript = artifact.get('transcript') or []
    if isinstance(transcript, list) and transcript:
        entries = [_normalize_transcript_entry(index, item) for index, item in enumerate(transcript, start=1)]
        logger.info('Extracted %s transcript entries from call.artifact.transcript', len(entries))
        return entries
    if isinstance(transcript, str) and transcript.strip():
        entries = _parse_transcript_string(transcript)
        if entries:
            logger.info('Extracted %s transcript entries from call.artifact.transcript string', len(entries))
            return entries

    messages = call_data.get('messages') or artifact.get('messages') or []
    if isinstance(messages, list) and messages:
        entries = [
            _normalize_message_entry(index, item)
            for index, item in enumerate(messages, start=1)
            if str((item or {}).get('role') or '').lower() != 'system'
        ]
        logger.info('Extracted %s transcript entries from call.messages fallback', len(entries))
        return entries

    logger.info('No transcript entries found in Vapi call payload.')
    return []


def _start_active_monitor(call_result: dict[str, Any]) -> None:
    if websocket is None:
        _append_monitor_error('websocket-client not installed; live audio monitor unavailable.')
        logger.warning('websocket-client not installed; skipping live audio monitor.')
        return

    listen_url = (((call_result or {}).get('monitor') or {}).get('listenUrl'))
    if not listen_url:
        _append_monitor_error('No monitor.listenUrl in Vapi call response.')
        logger.warning('No monitor.listenUrl in Vapi response; cannot start live audio monitor.')
        return

    call_id = call_result.get('id')
    audio_format, sample_rate = _determine_audio_format(call_result)
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_monitor_worker,
        args=(listen_url, call_id, audio_format, sample_rate, stop_event),
        daemon=True,
        name=f'vapi-monitor-{call_id}',
    )
    _active_monitor.update({'thread': thread, 'stop_event': stop_event, 'call_id': call_id})
    with _state_lock:
        _voice_agent_state['monitorStatus'] = 'connecting'
        _voice_agent_state['audioFormat'] = audio_format
        _voice_agent_state['sampleRate'] = sample_rate
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)
    logger.info(
        'Starting live audio monitor for call_id=%s listenUrl=%s format=%s sampleRate=%s',
        call_id,
        listen_url,
        audio_format,
        sample_rate,
    )
    thread.start()


def _stop_active_monitor() -> None:
    stop_event = _active_monitor.get('stop_event')
    thread = _active_monitor.get('thread')
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)
    _active_monitor.update({'thread': None, 'stop_event': None, 'call_id': None})


def _monitor_worker(listen_url: str, call_id: str | None, audio_format: str, sample_rate: int, stop_event: threading.Event) -> None:
    ws = None
    chunk_buffer = bytearray()
    try:
        ws = websocket.create_connection(listen_url, timeout=5)
        with _state_lock:
            _voice_agent_state['monitorStatus'] = 'connected'
            _voice_agent_state['updatedAt'] = int(time.time() * 1000)
        logger.info('Live audio monitor connected for call_id=%s', call_id)

        min_chunk_size = max(sample_rate * TRANSCRIBE_CHUNK_SECONDS, 32000)
        while not stop_event.is_set():
            try:
                frame = ws.recv()
            except websocket.WebSocketTimeoutException:
                if chunk_buffer:
                    _transcribe_audio_chunk(bytes(chunk_buffer), call_id, audio_format, sample_rate)
                    chunk_buffer.clear()
                continue

            if frame is None:
                break
            if isinstance(frame, (bytes, bytearray)):
                chunk_buffer.extend(frame)
                with _state_lock:
                    _voice_agent_state['audioBytesReceived'] += len(frame)
                    _voice_agent_state['updatedAt'] = int(time.time() * 1000)
                if len(chunk_buffer) >= min_chunk_size:
                    _transcribe_audio_chunk(bytes(chunk_buffer), call_id, audio_format, sample_rate)
                    chunk_buffer.clear()
            else:
                logger.info('Live audio monitor control message for call_id=%s message=%s', call_id, _truncate_for_log(frame, 400))

        if chunk_buffer:
            _transcribe_audio_chunk(bytes(chunk_buffer), call_id, audio_format, sample_rate)
    except Exception as exc:
        _append_monitor_error(f'Audio monitor error: {str(exc)}')
        logger.error('Live audio monitor failed for call_id=%s error=%s', call_id, str(exc))
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        with _state_lock:
            _voice_agent_state['monitorStatus'] = 'stopped'
            _voice_agent_state['updatedAt'] = int(time.time() * 1000)
        logger.info('Live audio monitor stopped for call_id=%s', call_id)


def _transcribe_audio_chunk(audio_bytes: bytes, call_id: str | None, audio_format: str, sample_rate: int) -> None:
    if not audio_bytes:
        return
    if _openai_client is None:
        _append_monitor_error('No OpenAI API key available for live transcription.')
        logger.warning('Skipping live transcription for call_id=%s because OPENAI_API_KEY is missing.', call_id)
        return

    try:
        wav_bytes = _raw_audio_to_wav(audio_bytes, audio_format, sample_rate)
        file_obj = io.BytesIO(wav_bytes)
        file_obj.name = f'call-{call_id or "unknown"}-chunk.wav'
        logger.info(
            'Submitting live audio chunk for transcription call_id=%s bytes=%s format=%s sampleRate=%s',
            call_id,
            len(audio_bytes),
            audio_format,
            sample_rate,
        )
        transcript = _openai_client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=file_obj,
        )
        transcript_text = getattr(transcript, 'text', '') or ''
        if not transcript_text.strip():
            logger.info('Live transcription returned empty text for call_id=%s', call_id)
            return
        logger.info('Live transcription call_id=%s text=%s', call_id, _truncate_for_log(transcript_text, 500))
        _append_transcript_segment(transcript_text)
    except Exception as exc:
        _append_monitor_error(f'Transcription error: {str(exc)}')
        logger.error('Live transcription failed for call_id=%s error=%s', call_id, str(exc))


def _raw_audio_to_wav(audio_bytes: bytes, audio_format: str, sample_rate: int) -> bytes:
    pcm_bytes = audio_bytes
    sample_width = 2
    if audio_format == 'mulaw':
        pcm_bytes = _mulaw_to_pcm16(audio_bytes)
        sample_width = 2
    elif audio_format == 'pcm_s16le':
        sample_width = 2
    else:
        raise ValueError(f'Unsupported audio format: {audio_format}')

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _append_transcript_segment(text: str) -> None:
    cleaned = str(text).strip()
    if not cleaned:
        return
    with _state_lock:
        segments = list(_voice_agent_state.get('transcriptSegments') or [])
        if segments and segments[-1] == cleaned:
            return
        segments.append(cleaned)
        transcript_text = ' '.join(segments).strip()
        _voice_agent_state['transcriptSegments'] = segments
        _voice_agent_state['transcriptText'] = transcript_text
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)

    parsed_order = parse_order_from_transcript(transcript_text)
    missing_fields = [
        field
        for field in REQUIRED_ORDER_FIELDS
        if parsed_order.get(field) in [None, '', 0]
    ]
    with _state_lock:
        _voice_agent_state['ready'] = len(missing_fields) == 0
        _voice_agent_state['order'] = parsed_order if len(missing_fields) == 0 else None
        _voice_agent_state['missingFields'] = missing_fields
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)
    logger.info(
        'Parsed live transcript ready=%s missing=%s order=%s',
        len(missing_fields) == 0,
        missing_fields,
        parsed_order,
    )


def parse_order_from_transcript(transcript_text: str) -> dict[str, Any]:
    text = str(transcript_text or '').strip()
    normalized = text.lower()
    user_text = _extract_user_utterances(text) or text
    user_normalized = user_text.lower()
    product = _extract_product_from_transcript(user_text)
    quantity = _extract_quantity(user_normalized)
    requested_price = _extract_price(user_normalized)
    requested_delivery_days = _extract_delivery_days(user_normalized)
    customer = _extract_customer_name(user_text)
    priority = 'rush' if any(term in normalized for term in ['rush', 'urgent', 'critical']) else 'standard'

    return {
        'id': f'ORD-VOICE-{str(int(time.time() * 1000))[-6:]}',
        'customer': customer or 'Voice Customer',
        'product': product,
        'quantity': quantity,
        'requestedPrice': requested_price,
        'requestedDeliveryDays': requested_delivery_days,
        'priority': priority,
    }


def _append_monitor_error(message: str) -> None:
    with _state_lock:
        errors = list(_voice_agent_state.get('monitorErrors') or [])
        errors.append(message)
        _voice_agent_state['monitorErrors'] = errors[-10:]
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)


def _determine_audio_format(call_result: dict[str, Any]) -> tuple[str, int]:
    if FORCE_MONITOR_AUDIO_FORMAT:
        forced = FORCE_MONITOR_AUDIO_FORMAT.strip().lower()
        if forced == 'mulaw':
            return 'mulaw', DEFAULT_MULAW_SAMPLE_RATE
        return 'pcm_s16le', DEFAULT_PCM_SAMPLE_RATE

    provider = str(call_result.get('phoneCallProvider') or '').lower()
    if provider in {'twilio', 'telnyx', 'plivo'}:
        return 'mulaw', DEFAULT_MULAW_SAMPLE_RATE
    return 'pcm_s16le', DEFAULT_PCM_SAMPLE_RATE


def _merge_fallback_transcript(call_data: dict[str, Any], transcript_entries: list[dict[str, Any]], transcript_text: str) -> None:
    parsed_order = _extract_order_from_full_transcript(transcript_text)
    missing_fields = [
        field
        for field in REQUIRED_ORDER_FIELDS
        if parsed_order.get(field) in [None, '', 0]
    ]
    with _state_lock:
        _voice_agent_state['lastCall'] = call_data
        _voice_agent_state['lastCallId'] = call_data.get('id') or _voice_agent_state.get('lastCallId')
        _voice_agent_state['transcriptSegments'] = [entry.get('text', '') for entry in transcript_entries if entry.get('text')]
        _voice_agent_state['transcriptText'] = transcript_text
        if transcript_entries:
            _voice_agent_state['lastPayloadKeys'] = ['vapi-call-fallback']
            _voice_agent_state['lastPayloadPreview'] = {'transcriptEntries': transcript_entries[:5]}
        if len(missing_fields) == 0:
            _voice_agent_state['ready'] = True
            _voice_agent_state['order'] = parsed_order
            _voice_agent_state['missingFields'] = []
        else:
            _voice_agent_state['missingFields'] = missing_fields
        _voice_agent_state['updatedAt'] = int(time.time() * 1000)
    logger.info(
        'Merged fallback transcript for call_id=%s ready=%s missing=%s order=%s',
        call_data.get('id'),
        len(missing_fields) == 0,
        missing_fields,
        parsed_order,
    )


def _extract_order_from_full_transcript(transcript_text: str) -> dict[str, Any]:
    llm_order = _extract_order_with_llm(transcript_text)
    if llm_order is not None:
        return llm_order
    return parse_order_from_transcript(transcript_text)


def _extract_order_with_llm(transcript_text: str) -> dict[str, Any] | None:
    if _openai_client is None:
        return None
    transcript = str(transcript_text or '').strip()
    if not transcript:
        return None

    sku_hint = ', '.join(KNOWN_SKUS) if KNOWN_SKUS else 'PMP-STD-100, PMP-HEAVY-200, PMP-CHEM-300'
    try:
        completion = _openai_client.beta.chat.completions.parse(
            model=VOICE_STRUCTURED_MODEL,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Extract the customer order from this phone transcript. '
                        'Return only the structured fields. '
                        f'Valid product SKUs are: {sku_hint}. '
                        'Map noisy transcript variants to the closest valid SKU. '
                        'Use integers for quantity and delivery days, float for requestedPrice. '
                        'If a field is not stated, return null. '
                        'Priority should be rush or standard.'
                    ),
                },
                {
                    'role': 'user',
                    'content': transcript,
                },
            ],
            response_format=VoiceOrderStructuredOutput,
        )
        message = completion.choices[0].message
        parsed = getattr(message, 'parsed', None)
        if parsed is None:
            logger.warning('Structured transcript extraction returned no parsed output.')
            return None
        structured_order = _normalize_llm_order(parsed.model_dump())
        logger.info('Structured transcript extraction succeeded: %s', structured_order)
        return structured_order
    except Exception as exc:
        logger.warning('Structured transcript extraction failed: %s', str(exc))
        return None


def _normalize_transcript_entry(index: int, item: dict[str, Any]) -> dict[str, Any]:
    role = str(item.get('role') or '').lower()
    sender = 'agent' if role == 'assistant' else 'customer' if role == 'user' else role or 'agent'
    return {
        'id': index,
        'sender': sender,
        'role': role or sender,
        'text': str(item.get('message') or '').strip(),
        'time': item.get('time'),
    }


def _normalize_message_entry(index: int, item: dict[str, Any]) -> dict[str, Any]:
    role = str(item.get('role') or '').lower()
    sender = 'agent' if role == 'assistant' else 'customer' if role == 'user' else role or 'agent'
    return {
        'id': index,
        'sender': sender,
        'role': role or sender,
        'text': str(item.get('message') or item.get('content') or '').strip(),
        'time': item.get('time') or item.get('secondsFromStart'),
    }


def _parse_transcript_string(transcript: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pattern = re.compile(r'^\s*(AI|User)\s*:\s*(.+?)\s*$', re.IGNORECASE | re.MULTILINE)
    for index, match in enumerate(pattern.finditer(transcript), start=1):
        role = match.group(1).strip().lower()
        text = match.group(2).strip()
        sender = 'agent' if role == 'ai' else 'customer'
        entries.append(
            {
                'id': index,
                'sender': sender,
                'role': 'assistant' if role == 'ai' else 'user',
                'text': text,
                'time': None,
            }
        )
    return entries


def _serialize_transcript_entries(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in entries:
        role = str(entry.get('role') or '').lower()
        speaker = 'User' if role == 'user' else 'AI'
        text = str(entry.get('text') or '').strip()
        if text:
            lines.append(f'{speaker}: {text}')
    return '\n'.join(lines).strip()


def _extract_user_utterances(text: str) -> str:
    matches = re.findall(r'^\s*User\s*:\s*(.+?)\s*$', text, flags=re.IGNORECASE | re.MULTILINE)
    return ' '.join(match.strip() for match in matches if str(match).strip())


def _extract_customer_name(text: str) -> str | None:
    match = re.search(r'\bthis is ([a-z][a-z .-]{1,60}?)(?:[.,!?]|$)', text, flags=re.IGNORECASE)
    if not match:
        return None
    return ' '.join(part.capitalize() for part in match.group(1).split())


def _extract_quantity(text: str) -> int | None:
    digit_match = re.search(r'\b(\d{1,6})\s*(?:units?|pieces?)\b', text)
    if digit_match:
        return int(digit_match.group(1))
    word_match = re.search(r'\b([a-z -]+?)\s*(?:units?|pieces?)\b', text)
    if word_match:
        return _words_to_number(word_match.group(1))
    return None


def _extract_price(text: str) -> float | None:
    digit_match = re.search(r'(?:\$|usd\s*|price\s*(?:is|of|would be|is at)?\s*)(\d+(?:\.\d+)?)', text)
    if digit_match:
        return float(digit_match.group(1))
    word_match = re.search(r'(?:price\s*(?:is|of|would be|is at)?\s*|target price (?:is|would be)?\s*)([a-z -]+?)\s+dollars?', text)
    if word_match:
        value = _words_to_number(word_match.group(1))
        if value is not None:
            return float(value)
    return None


def _extract_delivery_days(text: str) -> int | None:
    digit_match = re.search(r'\b(\d{1,3})\s*days?\b', text)
    if digit_match:
        return int(digit_match.group(1))
    word_match = re.search(r'\bwithin\s+([a-z -]+?)\s+days?\b', text)
    if word_match:
        return _words_to_number(word_match.group(1))
    return None


def _extract_product_from_transcript(text: str) -> str | None:
    sku_match = re.search(r'\b([A-Z]{2,}(?:-[A-Z0-9]+)+)\b', text)
    if sku_match:
        return sku_match.group(1)

    normalized = re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()
    if re.search(r'\bpmp\w*\s+(?:(?:one\s+)?hundred|100)\b', normalized):
        return 'PMP-STD-100'
    if re.search(r'\bpmp\w*\s+(?:two hundred|200)\b', normalized):
        return 'PMP-HEAVY-200'
    if re.search(r'\bpmp\w*\s+(?:three hundred|300)\b', normalized):
        return 'PMP-CHEM-300'

    compact = re.sub(r'[^a-z0-9]+', '', normalized)
    for sku in KNOWN_SKUS:
        sku_compact = re.sub(r'[^a-z0-9]+', '', sku.lower())
        if sku_compact and sku_compact in compact:
            return sku
    return None


def _normalize_llm_order(order: dict[str, Any]) -> dict[str, Any]:
    product = _normalize_llm_product(order.get('product'))
    quantity = _safe_int(order.get('quantity'), None)
    requested_price = _safe_float(order.get('requestedPrice'), None)
    requested_delivery_days = _safe_int(order.get('requestedDeliveryDays'), None)
    customer = _normalize_customer_name(order.get('customer'))
    priority = _normalize_priority(order.get('priority')) or 'rush'
    return {
        'id': f'ORD-VOICE-{str(int(time.time() * 1000))[-6:]}',
        'customer': customer or 'Voice Customer',
        'product': product,
        'quantity': quantity,
        'requestedPrice': requested_price,
        'requestedDeliveryDays': requested_delivery_days,
        'priority': priority,
    }


def _normalize_llm_product(value: Any) -> str | None:
    if value in [None, '']:
        return None
    raw = str(value).strip()
    if raw in KNOWN_SKUS:
        return raw
    mapped = _extract_product_from_transcript(raw)
    if mapped:
        return mapped
    return None


def _normalize_customer_name(value: Any) -> str | None:
    if value in [None, '']:
        return None
    text = re.sub(r'\s+', ' ', str(value)).strip(' .,!?\n\t')
    return text or None


def _words_to_number(value: str) -> int | None:
    words = re.sub(r'[^a-z -]+', ' ', str(value).lower()).replace('-', ' ').split()
    if not words:
        return None

    small_numbers = {
        'zero': 0,
        'one': 1,
        'two': 2,
        'three': 3,
        'four': 4,
        'five': 5,
        'six': 6,
        'seven': 7,
        'eight': 8,
        'nine': 9,
        'ten': 10,
        'eleven': 11,
        'twelve': 12,
        'thirteen': 13,
        'fourteen': 14,
        'fifteen': 15,
        'sixteen': 16,
        'seventeen': 17,
        'eighteen': 18,
        'nineteen': 19,
        'twenty': 20,
        'thirty': 30,
        'forty': 40,
        'fifty': 50,
        'sixty': 60,
        'seventy': 70,
        'eighty': 80,
        'ninety': 90,
    }
    scales = {'hundred': 100, 'thousand': 1000}
    total = 0
    current = 0

    for word in words:
        if word in {'and', 'a', 'an', 'per', 'unit', 'units', 'used'}:
            continue
        if word.isdigit():
            current += int(word)
            continue
        if word in small_numbers:
            current += small_numbers[word]
            continue
        if word in scales:
            scale = scales[word]
            current = max(current, 1) * scale
            if scale >= 1000:
                total += current
                current = 0
            continue
        return None

    return total + current if (total + current) > 0 else None


def _vapi_request(method: str, path: str, params: dict[str, Any] | None = None) -> Any:
    if not VAPI_API_KEY:
        raise RuntimeError('Missing VAPI_API_KEY.')

    headers = {
        'Authorization': f'Bearer {VAPI_API_KEY}',
        'Content-Type': 'application/json',
    }
    url = f'{BASE_URL}{path}'
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        timeout=15,
    )
    logger.info('Vapi %s %s response status=%s', method, path, response.status_code)
    response.raise_for_status()
    response_json = response.json()
    logger.info('Vapi %s %s response body=%s', method, path, _truncate_for_log(response_json))
    return response_json


def _get_vapi_client() -> Vapi:
    if _vapi_client is None:
        raise RuntimeError('Missing VAPI_API_KEY.')
    return _vapi_client


def _sdk_to_dict(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return value.model_dump(by_alias=True)
    if isinstance(value, list):
        return [_sdk_to_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_sdk_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _sdk_to_dict(item) for key, item in value.items()}
    return value


def _mulaw_to_pcm16(data: bytes) -> bytes:
    output = bytearray()
    for value in data:
        output.extend(_mulaw_sample_to_pcm16(value))
    return bytes(output)


def _mulaw_sample_to_pcm16(value: int) -> bytes:
    ulaw = (~value) & 0xFF
    sign = ulaw & 0x80
    exponent = (ulaw >> 4) & 0x07
    mantissa = ulaw & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    if sign:
        sample = -sample
    return int(sample).to_bytes(2, byteorder='little', signed=True)
