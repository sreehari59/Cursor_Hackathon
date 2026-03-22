import { NextResponse } from "next/server"
import { BASELINE } from "@/lib/synk/baseline-data"

// GET /api/baseline — Retrieve operational baseline parameters used by all agents
export async function GET() {
  return NextResponse.json({
    production: {
      capacityPerWeek: BASELINE.productionCapacity,
      standardLeadTimeDays: BASELINE.standardLeadTimeDays,
      overtimeCostPerHour: BASELINE.overtimeCostPerHour,
      maxOvertimeHoursPerDay: BASELINE.maxOvertimeHoursPerDay,
      workingDaysPerWeek: BASELINE.workingDaysPerWeek,
    },
    finance: {
      baseCostPerUnit: BASELINE.baseCostPerUnit,
      marginFloor: BASELINE.marginFloor,
      targetMargin: BASELINE.targetMargin,
      rushSurchargeRate: BASELINE.rushSurchargeRate,
    },
    logistics: {
      shippingModes: {
        ground: { costPerUnit: BASELINE.groundCostPerUnit, transitDays: BASELINE.groundShippingDays },
        express: { costPerUnit: BASELINE.expressCostPerUnit, transitDays: BASELINE.expressShippingDays },
        air: { costPerUnit: BASELINE.airCostPerUnit, transitDays: BASELINE.airShippingDays },
      },
    },
    procurement: {
      primary: { supplier: BASELINE.primarySupplier, leadTimeDays: BASELINE.primaryLeadTimeDays, costPerUnit: BASELINE.materialCostPerUnit },
      alternate: { supplier: BASELINE.alternateSupplier, leadTimeDays: BASELINE.alternateLeadTimeDays, costPerUnit: BASELINE.alternateMaterialCostPerUnit },
    },
    sales: {
      customerTier: BASELINE.customerTier,
      relationshipYears: BASELINE.relationshipYears,
      annualVolume: BASELINE.annualVolume,
      acceptableDeliveryBuffer: BASELINE.acceptableDeliveryBuffer,
    },
  })
}
