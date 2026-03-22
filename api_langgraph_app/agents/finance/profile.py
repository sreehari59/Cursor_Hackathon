AGENT_PROFILE = {
    'id': 'finance',
    'name': 'Finance',
    'role': 'Margins & Pricing',
    'color': '#10b981',
}


def get_description(baseline):
    return (
        f"Enforces margin floor ({int(baseline['marginFloor'] * 100)}%), target margin "
        f"({int(baseline['targetMargin'] * 100)}%), and negotiates pricing with rush "
        f"surcharge capability ({int(baseline['rushSurchargeRate'] * 100)}%)."
    )


def get_operational_parameters(baseline):
    return {
        'baseCostPerUnit': baseline['baseCostPerUnit'],
        'marginFloor': baseline['marginFloor'],
        'targetMargin': baseline['targetMargin'],
        'rushSurchargeRate': baseline['rushSurchargeRate'],
    }
