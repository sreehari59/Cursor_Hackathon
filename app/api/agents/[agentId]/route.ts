import { NextResponse } from "next/server"
import { AGENT_CONFIGS, type AgentId } from "@/lib/synk/types"
import { BASELINE } from "@/lib/synk/baseline-data"

// GET /api/agents/:agentId — Get a specific agent's full profile and operational parameters
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ agentId: string }> }
) {
  const { agentId } = await params
  const config = AGENT_CONFIGS.find(a => a.id === agentId)

  if (!config) {
    return NextResponse.json({ error: `Agent '${agentId}' not found` }, { status: 404 })
  }

  const operationalParams = getOperationalParams(agentId as AgentId)

  return NextResponse.json({
    id: config.id,
    name: config.name,
    role: config.role,
    color: config.color,
    avatar: `/agents/${config.id}.jpg`,
    operationalParameters: operationalParams,
  })
}

function getOperationalParams(agentId: AgentId): Record<string, unknown> {
  switch (agentId) {
    case "production":
      return {
        capacity: BASELINE.productionCapacity,
        standardLeadTime: BASELINE.standardLeadTimeDays,
        maxOvertimePerDay: BASELINE.maxOvertimeHoursPerDay,
        overtimeCostPerHour: BASELINE.overtimeCostPerHour,
        workingDaysPerWeek: BASELINE.workingDaysPerWeek,
      }
    case "finance":
      return {
        baseCostPerUnit: BASELINE.baseCostPerUnit,
        marginFloor: BASELINE.marginFloor,
        targetMargin: BASELINE.targetMargin,
        rushSurchargeRate: BASELINE.rushSurchargeRate,
      }
    case "logistics":
      return {
        shippingModes: {
          ground: { cost: BASELINE.groundCostPerUnit, transitDays: BASELINE.groundShippingDays },
          express: { cost: BASELINE.expressCostPerUnit, transitDays: BASELINE.expressShippingDays },
          air: { cost: BASELINE.airCostPerUnit, transitDays: BASELINE.airShippingDays },
        },
      }
    case "procurement":
      return {
        primarySupplier: { name: BASELINE.primarySupplier, leadTime: BASELINE.primaryLeadTimeDays, costPerUnit: BASELINE.materialCostPerUnit },
        alternateSupplier: { name: BASELINE.alternateSupplier, leadTime: BASELINE.alternateLeadTimeDays, costPerUnit: BASELINE.alternateMaterialCostPerUnit },
      }
    case "sales":
      return {
        customerTier: BASELINE.customerTier,
        relationshipYears: BASELINE.relationshipYears,
        annualVolume: BASELINE.annualVolume,
        acceptableDeliveryBuffer: BASELINE.acceptableDeliveryBuffer,
      }
  }
}
