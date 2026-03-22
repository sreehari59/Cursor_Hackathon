from ..constants import BASELINE
from .finance import (
    AGENT_PROFILE as FINANCE_PROFILE,
    TOOLS as FINANCE_TOOLS,
    get_description as finance_description,
    get_operational_parameters as finance_operational_parameters,
)
from .logistics import (
    AGENT_PROFILE as LOGISTICS_PROFILE,
    TOOLS as LOGISTICS_TOOLS,
    get_description as logistics_description,
    get_operational_parameters as logistics_operational_parameters,
)
from .procurement import (
    AGENT_PROFILE as PROCUREMENT_PROFILE,
    TOOLS as PROCUREMENT_TOOLS,
    get_description as procurement_description,
    get_operational_parameters as procurement_operational_parameters,
)
from .production import (
    AGENT_PROFILE as PRODUCTION_PROFILE,
    TOOLS as PRODUCTION_TOOLS,
    get_description as production_description,
    get_operational_parameters as production_operational_parameters,
)
from .sales import (
    AGENT_PROFILE as SALES_PROFILE,
    TOOLS as SALES_TOOLS,
    get_description as sales_description,
    get_operational_parameters as sales_operational_parameters,
)


AGENT_DETAILS = {
    'production': {
        'profile': PRODUCTION_PROFILE,
        'tools': PRODUCTION_TOOLS,
        'description_fn': production_description,
        'params_fn': production_operational_parameters,
    },
    'finance': {
        'profile': FINANCE_PROFILE,
        'tools': FINANCE_TOOLS,
        'description_fn': finance_description,
        'params_fn': finance_operational_parameters,
    },
    'logistics': {
        'profile': LOGISTICS_PROFILE,
        'tools': LOGISTICS_TOOLS,
        'description_fn': logistics_description,
        'params_fn': logistics_operational_parameters,
    },
    'procurement': {
        'profile': PROCUREMENT_PROFILE,
        'tools': PROCUREMENT_TOOLS,
        'description_fn': procurement_description,
        'params_fn': procurement_operational_parameters,
    },
    'sales': {
        'profile': SALES_PROFILE,
        'tools': SALES_TOOLS,
        'description_fn': sales_description,
        'params_fn': sales_operational_parameters,
    },
}

AGENT_IDS = list(AGENT_DETAILS.keys())
AGENT_CONFIGS = [AGENT_DETAILS[agent_id]['profile'] for agent_id in AGENT_IDS]


def get_agent_tools(agent_id):
    details = AGENT_DETAILS.get(agent_id)
    if not details:
        return []
    return details['tools']


def get_agent_description(agent_id):
    details = AGENT_DETAILS.get(agent_id)
    if not details:
        return ''
    return details['description_fn'](BASELINE)


def get_operational_parameters(agent_id):
    details = AGENT_DETAILS.get(agent_id)
    if not details:
        return {}
    return details['params_fn'](BASELINE)
