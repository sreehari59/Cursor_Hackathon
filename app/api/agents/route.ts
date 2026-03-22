import { NextResponse } from "next/server"
import { AGENT_CONFIGS } from "@/lib/synk/types"
import { BASELINE } from "@/lib/synk/baseline-data"

// GET /api/agents — List all agents with their profiles, roles, and available tools
export async function GET() {
  const agentProfiles = AGENT_CONFIGS.map(agent => {
    const tools = getAgentTools(agent.id)
    return {
      id: agent.id,
      name: agent.name,
      role: agent.role,
      color: agent.color,
      avatar: `/agents/${agent.id}.jpg`,
      tools,
      description: getAgentDescription(agent.id),
    }
  })

  return NextResponse.json({ agents: agentProfiles })
}

function getAgentTools(agentId: string): { name: string; description: string; parameters: Record<string, string> }[] {
  switch (agentId) {
    case "production":
      return [
        { name: "check_production_capacity", description: "Query factory floor for available capacity and throughput", parameters: { quantity: "number", delivery_days: "number" } },
        { name: "calculate_overtime", description: "Compute overtime schedule and cost for production shortfall", parameters: { shortfall_days: "number", max_ot_per_day: "number" } },
        { name: "recalculate_schedule", description: "Re-evaluate production schedule with adjusted delivery window", parameters: { delivery_days: "number" } },
        { name: "lock_production_schedule", description: "Finalize and lock the production schedule", parameters: { delivery_days: "number", overtime_hours: "number" } },
      ]
    case "finance":
      return [
        { name: "compute_unit_economics", description: "Run margin analysis at a given price point", parameters: { price: "number", overtime_hours: "number" } },
        { name: "calculate_rush_surcharge", description: "Calculate rush surcharge to meet margin floor", parameters: { base_price: "number", surcharge_rate: "number" } },
        { name: "negotiate_price", description: "Open price negotiation with initial position", parameters: { initial_price: "number" } },
        { name: "compute_compromise", description: "Test a compromise price point against margin thresholds", parameters: { offer_price: "number" } },
        { name: "verify_final_margin", description: "Final margin verification at locked price", parameters: { final_price: "number" } },
      ]
    case "logistics":
      return [
        { name: "evaluate_shipping_modes", description: "Compare ground, express, and air freight for delivery window", parameters: { delivery_days: "number" } },
        { name: "check_route_clearance", description: "Verify carrier availability and route clearance", parameters: { origin: "string", destination: "string", quantity: "number" } },
        { name: "re_evaluate_mode", description: "Re-check shipping mode after delivery adjustment", parameters: { delivery_days: "number" } },
        { name: "book_carrier", description: "Book carrier and lock route for final delivery", parameters: { mode: "string", delivery_days: "number" } },
      ]
    case "procurement":
      return [
        { name: "query_supplier_inventory", description: "Check supplier for material availability and lead time", parameters: { supplier: "string", quantity: "number" } },
        { name: "query_alternate_supplier", description: "Check alternate supplier as backup option", parameters: { supplier: "string", quantity: "number" } },
        { name: "reserve_materials", description: "Reserve raw materials with selected supplier", parameters: { supplier: "string", quantity: "number" } },
        { name: "submit_purchase_order", description: "Submit final purchase order to supplier", parameters: { supplier: "string", quantity: "number", price_per_unit: "number" } },
      ]
    case "sales":
      return [
        { name: "lookup_customer_profile", description: "Retrieve customer tier, relationship history, and annual volume", parameters: { customer: "string" } },
        { name: "assess_deal_sensitivity", description: "Evaluate customer sensitivity to price changes", parameters: { customer: "string", proposed_price: "number" } },
        { name: "calculate_counter_offer", description: "Compute counter-offer balancing margin and customer retention", parameters: { proposed_price: "number", original_price: "number" } },
        { name: "calculate_deal_value", description: "Compute final deal metrics for customer report", parameters: { price: "number", quantity: "number" } },
      ]
    default:
      return []
  }
}

function getAgentDescription(agentId: string): string {
  switch (agentId) {
    case "production": return `Manages factory capacity (${BASELINE.productionCapacity} units/week), scheduling, and overtime allocation (max ${BASELINE.maxOvertimeHoursPerDay}h/day at $${BASELINE.overtimeCostPerHour}/hr).`
    case "finance": return `Enforces margin floor (${BASELINE.marginFloor * 100}%), target margin (${BASELINE.targetMargin * 100}%), and negotiates pricing with rush surcharge capability (${BASELINE.rushSurchargeRate * 100}%).`
    case "logistics": return `Optimizes shipping mode selection: ground ($${BASELINE.groundCostPerUnit}/u, ${BASELINE.groundShippingDays}d), express ($${BASELINE.expressCostPerUnit}/u, ${BASELINE.expressShippingDays}d), air ($${BASELINE.airCostPerUnit}/u, ${BASELINE.airShippingDays}d).`
    case "procurement": return `Manages supplier relationships: primary (${BASELINE.primarySupplier}, ${BASELINE.primaryLeadTimeDays}d lead) and alternate (${BASELINE.alternateSupplier}, ${BASELINE.alternateLeadTimeDays}d lead).`
    case "sales": return `Manages customer relationships. Acme Corp: ${BASELINE.customerTier} tier, ${BASELINE.relationshipYears}yr relationship, ${BASELINE.annualVolume.toLocaleString()} annual volume.`
    default: return ""
  }
}
