from flask import Blueprint, jsonify, request

from .. import state
from ..services import build_synk_order, run_process_order_for_synk


orders_bp = Blueprint('orders_api', __name__, url_prefix='/api')


@orders_bp.post('/orders')
def create_order():
    try:
        body = request.get_json(silent=True) or {}
        order = build_synk_order(body)

        process_response = None
        warning = None
        try:
            process_response, warning = run_process_order_for_synk(order, body)
        except Exception as process_err:
            warning = f'process_order failed: {str(process_err)}'
            state.logger.error(warning)

        payload = {
            'success': True,
            'order': order,
        }
        if process_response is not None:
            payload['processOrder'] = process_response
        if warning:
            payload['backendWarning'] = warning

        return jsonify(payload), 200
    except Exception as exc:
        state.logger.error('/api/orders failed: %s', exc)
        return jsonify({'error': str(exc)}), 500
