from flask import Blueprint, jsonify

from .. import state


health_bp = Blueprint('health_api', __name__, url_prefix='/api')


@health_bp.get('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Multi-Agent Order Processing System (LangGraph)',
        'llm_available': state.manager is not None,
    })
