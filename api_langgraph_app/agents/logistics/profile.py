AGENT_PROFILE = {
    'id': 'logistics',
    'name': 'Logistics',
    'role': 'Shipping & Delivery',
    'color': '#f59e0b',
}


def get_description(baseline):
    return (
        f"Optimizes shipping mode selection: ground (${baseline['groundCostPerUnit']}/u, "
        f"{baseline['groundShippingDays']}d), express (${baseline['expressCostPerUnit']}/u, "
        f"{baseline['expressShippingDays']}d), air (${baseline['airCostPerUnit']}/u, "
        f"{baseline['airShippingDays']}d)."
    )


def get_operational_parameters(baseline):
    return {
        'shippingModes': {
            'ground': {'cost': baseline['groundCostPerUnit'], 'transitDays': baseline['groundShippingDays']},
            'express': {'cost': baseline['expressCostPerUnit'], 'transitDays': baseline['expressShippingDays']},
            'air': {'cost': baseline['airCostPerUnit'], 'transitDays': baseline['airShippingDays']},
        }
    }
