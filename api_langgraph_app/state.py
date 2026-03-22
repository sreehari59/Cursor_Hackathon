import logging
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .agents.finance import LLMFinanceAgent
from .agents.logistics import LLMLogisticsAgent
from .agents.procurement import LLMProcurementAgent
from .agents.production import LLMProductionAgent
from .agents.sales import LLMSalesAgent
from .agents.runtime import InventoryManager, LLMManagerAgent


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

inventory_manager = None
manager = None
procurement_agent = None
production_agent = None
logistics_agent = None
finance_agent = None
sales_agent = None

def _is_truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


try:
    use_mock_process_order = _is_truthy(os.getenv('BACKEND_USE_MOCK_PROCESS_ORDER', 'false'))
    use_real_agent_pipeline = _is_truthy(os.getenv('BACKEND_USE_REAL_AGENT_PIPELINE', 'false'))
    inventory_manager = InventoryManager('data/inventory.json', 'data/materials.json')

    api_key = os.getenv('OPEN_AI_API_KEY')
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY')

    if use_mock_process_order:
        logger.info('BACKEND_USE_MOCK_PROCESS_ORDER=true, runtime is in mock process_order mode.')
        manager = None

        if use_real_agent_pipeline and api_key:
            shared_llm = ChatOpenAI(api_key=api_key, model='gpt-3.5-turbo', temperature=0.3)
            procurement_agent = LLMProcurementAgent(shared_llm, inventory_manager)
            production_agent = LLMProductionAgent(shared_llm, inventory_manager)
            logistics_agent = LLMLogisticsAgent(shared_llm, inventory_manager)
            finance_agent = LLMFinanceAgent(shared_llm, inventory_manager)
            sales_agent = LLMSalesAgent(shared_llm, inventory_manager)
            logger.info('Live agent pipeline enabled (BACKEND_USE_REAL_AGENT_PIPELINE=true).')
        elif use_real_agent_pipeline:
            logger.warning('BACKEND_USE_REAL_AGENT_PIPELINE=true but API key is missing. Falling back to mock response.')
    else:
        if not api_key:
            logger.warning('OPEN_AI_API_KEY not found in .env file. Using environment variable instead.')
        manager = LLMManagerAgent(api_key, inventory_manager)
        logger.info('LangGraph manager initialized successfully')
except Exception as exc:
    logger.error('Failed to initialize LangGraph manager: %s', exc)
    manager = None
    procurement_agent = None
    production_agent = None
    logistics_agent = None
    finance_agent = None
    sales_agent = None
