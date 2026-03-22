AGENT_PROFILE = {
    'id': 'production',
    'name': 'Production',
    'role': 'Manufacturing & Scheduling',
    'color': '#3b82f6',
}


def get_description(baseline):
    return (
        f"Manages factory capacity ({baseline['productionCapacity']} units/week), scheduling, "
        f"and overtime allocation (max {baseline['maxOvertimeHoursPerDay']}h/day at "
        f"${baseline['overtimeCostPerHour']}/hr)."
    )


def get_operational_parameters(baseline):
    return {
        'capacity': baseline['productionCapacity'],
        'standardLeadTime': baseline['standardLeadTimeDays'],
        'maxOvertimePerDay': baseline['maxOvertimeHoursPerDay'],
        'overtimeCostPerHour': baseline['overtimeCostPerHour'],
        'workingDaysPerWeek': baseline['workingDaysPerWeek'],
    }
