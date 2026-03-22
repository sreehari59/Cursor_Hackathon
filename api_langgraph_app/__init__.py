from flask import Flask, jsonify

from .routes.agents import agents_bp
from .routes.health import health_bp
from .routes.negotiation import negotiation_bp
from .routes.orders import orders_bp
from .routes.voice import voice_bp


def create_app():
    app = Flask(__name__)

    app.register_blueprint(health_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(negotiation_bp)
    app.register_blueprint(voice_bp)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({
            'status': 'FAILURE',
            'message': 'Endpoint not found',
        }), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({
            'status': 'FAILURE',
            'message': 'Internal server error',
        }), 500

    return app
