// ─── SYNK Baseline Operational Data ──────────────────────────────────────
// Derived from the SYNK concept paper's example scenario

export const BASELINE = {
  // Production
  productionCapacity: 4000, // units/week
  standardLeadTimeDays: 22,
  overtimeCostPerHour: 45,
  maxOvertimeHoursPerDay: 4,
  workingDaysPerWeek: 5,

  // Finance
  baseCostPerUnit: 8.50,
  marginFloor: 0.15, // 15% minimum margin
  targetMargin: 0.22, // 22% target margin
  rushSurchargeRate: 0.12, // 12% suggested uplift

  // Logistics
  groundShippingDays: 5,
  expressShippingDays: 3,
  airShippingDays: 1,
  groundCostPerUnit: 0.30,
  expressCostPerUnit: 0.85,
  airCostPerUnit: 2.10,

  // Procurement
  primarySupplier: "ChemCorp Asia",
  primaryLeadTimeDays: 10,
  alternateSupplier: "EuroChem GmbH",
  alternateLeadTimeDays: 14,
  materialCostPerUnit: 3.20,
  alternateMaterialCostPerUnit: 3.80,

  // Sales
  customerTier: "Strategic",
  relationshipYears: 5,
  annualVolume: 120000,
  acceptableDeliveryBuffer: 2, // days flexibility
}
