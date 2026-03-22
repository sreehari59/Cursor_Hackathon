AGENT_PROFILE = {
    'id': 'procurement',
    'name': 'Procurement',
    'role': 'Materials & Suppliers',
    'color': '#8b5cf6',
}


def get_description(baseline):
    return (
        f"Manages supplier relationships: primary ({baseline['primarySupplier']}, "
        f"{baseline['primaryLeadTimeDays']}d lead) and alternate "
        f"({baseline['alternateSupplier']}, {baseline['alternateLeadTimeDays']}d lead)."
    )


def get_operational_parameters(baseline):
    return {
        'primarySupplier': {
            'name': baseline['primarySupplier'],
            'leadTime': baseline['primaryLeadTimeDays'],
            'costPerUnit': baseline['materialCostPerUnit'],
        },
        'alternateSupplier': {
            'name': baseline['alternateSupplier'],
            'leadTime': baseline['alternateLeadTimeDays'],
            'costPerUnit': baseline['alternateMaterialCostPerUnit'],
        },
    }
