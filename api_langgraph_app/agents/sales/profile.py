AGENT_PROFILE = {
    'id': 'sales',
    'name': 'Sales',
    'role': 'Customer Relations',
    'color': '#ef4444',
}


def get_description(baseline):
    return (
        f"Manages customer relationships. Acme Corp: {baseline['customerTier']} tier, "
        f"{baseline['relationshipYears']}yr relationship, {baseline['annualVolume']} annual volume."
    )


def get_operational_parameters(baseline):
    return {
        'customerTier': baseline['customerTier'],
        'relationshipYears': baseline['relationshipYears'],
        'annualVolume': baseline['annualVolume'],
        'acceptableDeliveryBuffer': baseline['acceptableDeliveryBuffer'],
    }
