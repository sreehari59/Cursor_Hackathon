"""
Flask API entrypoint for LangGraph integration.
Routes are organized in api_langgraph_app/routes with Flask blueprints.
"""

from api_langgraph_app import create_app
from api_langgraph_app.state import logger


app = create_app()


if __name__ == '__main__':
    logger.info('Starting LangGraph-based Multi-Agent Order Processing System')
    logger.info('Endpoints available at http://localhost:8080/api')
    app.run(debug=False, host='0.0.0.0', port=8080)
