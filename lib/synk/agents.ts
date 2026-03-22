// ─── SYNK Agent Logic (Pure Functions) ───────────────────────────────────
import type { AgentProposal, Order, RoundSummary, ShippingMode, ActionStep } from "./types"
import { BASELINE } from "./baseline-data"

interface AgentInput {
  order: Order
  round: number
  previousRound?: RoundSummary
}

// ─── Production Agent ────────────────────────────────────────────────────
export function productionAgent({ order, round, previousRound }: AgentInput): AgentProposal {
  const deliveryDays = previousRound?.deliveryDays ?? order.requestedDeliveryDays
  const productionDays = deliveryDays - BASELINE.groundShippingDays
  const unitsPerDay = BASELINE.productionCapacity / BASELINE.workingDaysPerWeek
  const daysNeeded = Math.ceil(order.quantity / unitsPerDay)
  const overtimeNeeded = daysNeeded > productionDays

  if (round === 1) {
    const overtimeHours = overtimeNeeded ? Math.min(BASELINE.maxOvertimeHoursPerDay * (daysNeeded - productionDays), 20) : 0
    const actions: ActionStep[] = [
      {
        kind: "tool_call",
        label: "check_production_capacity()",
        detail: `Querying factory floor for available capacity. Current throughput: ${BASELINE.productionCapacity} units/week, ${BASELINE.workingDaysPerWeek} working days.`,
        data: { "Capacity": `${BASELINE.productionCapacity}/wk`, "Work Days": BASELINE.workingDaysPerWeek },
      },
      {
        kind: "tool_result",
        label: "capacity_analysis",
        detail: `${order.quantity} units require ${daysNeeded} production days. Available window: ${productionDays} days (delivery ${deliveryDays}d minus ${BASELINE.groundShippingDays}d shipping).`,
        data: { "Days Needed": daysNeeded, "Days Available": productionDays, "Shortfall": overtimeNeeded ? `${daysNeeded - productionDays}d` : "None" },
      },
      ...(overtimeNeeded ? [{
        kind: "tool_call" as const,
        label: "calculate_overtime()",
        detail: `Shortfall detected. Computing overtime schedule at max ${BASELINE.maxOvertimeHoursPerDay}h/day, $${BASELINE.overtimeCostPerHour}/hr.`,
        data: { "Max OT/Day": `${BASELINE.maxOvertimeHoursPerDay}h`, "OT Cost": `$${BASELINE.overtimeCostPerHour}/hr` },
      },
      {
        kind: "tool_result" as const,
        label: "overtime_schedule",
        detail: `Overtime required: ${overtimeHours}h total across ${daysNeeded - productionDays} days. Additional cost: $${(overtimeHours * BASELINE.overtimeCostPerHour).toLocaleString()}.`,
        data: { "Total OT": `${overtimeHours}h`, "OT Cost": `$${(overtimeHours * BASELINE.overtimeCostPerHour).toLocaleString()}` },
      }] : []),
      {
        kind: overtimeNeeded ? "response" : "agreement",
        label: overtimeNeeded ? "feasible_with_adjustments" : "capacity_sufficient",
        detail: overtimeNeeded
          ? `Production feasible with ${overtimeHours}h overtime. Standard lead is ${BASELINE.standardLeadTimeDays} days -- this is tight but doable.`
          : `Capacity check passed. ${productionDays} production days sufficient for ${order.quantity} units.`,
      },
    ]

    return {
      agentId: "production", round,
      status: overtimeNeeded ? "proposing" : "agreed",
      reasoning: overtimeNeeded
        ? `Need ${daysNeeded} production days but only have ${productionDays}. Overtime of ${overtimeHours}h required.`
        : `Capacity check passed. ${productionDays} days sufficient.`,
      metrics: { "Days Needed": daysNeeded, "Available": productionDays, "Overtime": overtimeNeeded ? `${overtimeHours}h` : "0h", "Feasible": overtimeNeeded ? "With OT" : "Yes" },
      approved: !overtimeNeeded || daysNeeded - productionDays <= 5,
      actions,
    }
  }

  const adjustedDays = previousRound?.deliveryDays ?? deliveryDays
  const adjustedProductionDays = adjustedDays - BASELINE.groundShippingDays
  const newOvertimeNeeded = daysNeeded > adjustedProductionDays
  const overtimeHours = newOvertimeNeeded ? Math.min(BASELINE.maxOvertimeHoursPerDay * (daysNeeded - adjustedProductionDays), 16) : 0

  const actions: ActionStep[] = round === 2 ? [
    {
      kind: "tool_call",
      label: "recalculate_schedule(delivery_days=" + adjustedDays + ")",
      detail: `Re-evaluating production with adjusted ${adjustedDays}-day delivery window from Logistics.`,
    },
    {
      kind: "tool_result",
      label: "adjusted_schedule",
      detail: `Production days now: ${adjustedProductionDays}. Overtime reduced from 12h to ${overtimeHours}h. Cost savings: $${((12 - overtimeHours) * BASELINE.overtimeCostPerHour).toLocaleString()}.`,
      data: { "New Window": `${adjustedProductionDays}d`, "Overtime": `${overtimeHours}h`, "Savings": `$${((12 - overtimeHours) * BASELINE.overtimeCostPerHour).toLocaleString()}` },
    },
    {
      kind: "response",
      label: "schedule_adjusted",
      detail: `Schedule feasible with adjusted timeline. Overtime at ${overtimeHours}h is within acceptable limits.`,
    },
  ] : [
    {
      kind: "tool_call",
      label: "lock_production_schedule()",
      detail: `Finalizing production schedule for ${adjustedDays}-day delivery.`,
    },
    {
      kind: "tool_result",
      label: "schedule_locked",
      detail: `Production schedule locked. ${adjustedProductionDays} production days, ${overtimeHours}h overtime confirmed. Resources allocated.`,
      data: { "Status": "LOCKED", "Overtime": `${overtimeHours}h`, "Delivery": `Day ${adjustedDays}` },
    },
    {
      kind: "agreement",
      label: "production_approved",
      detail: `Final verification complete. No objections. Production schedule locked.`,
    },
  ]

  return {
    agentId: "production", round,
    status: round === 3 ? "agreed" : "proposing",
    reasoning: round === 2
      ? `Recalculated with ${adjustedDays}-day delivery. OT reduced to ${overtimeHours}h.`
      : `Schedule locked. ${adjustedDays}-day delivery, ${overtimeHours}h overtime confirmed.`,
    metrics: { "Delivery": `${adjustedDays}d`, "Overtime": `${overtimeHours}h`, "Status": round === 3 ? "Locked" : "Adjusted" },
    approved: true,
    actions,
  }
}

// ─── Finance Agent ───────────────────────────────────────────────────────
export function financeAgent({ order, round, previousRound }: AgentInput): AgentProposal {
  const price = previousRound?.price ?? order.requestedPrice
  const overtimeHours = previousRound?.overtimeHours ?? 12
  const overtimeCost = (overtimeHours * BASELINE.overtimeCostPerHour) / order.quantity
  const totalCost = BASELINE.baseCostPerUnit + overtimeCost
  const margin = (price - totalCost) / price

  if (round === 1) {
    const belowFloor = margin < BASELINE.marginFloor
    const actions: ActionStep[] = [
      {
        kind: "tool_call",
        label: "compute_unit_economics(price=$" + price.toFixed(2) + ")",
        detail: `Running margin analysis. Base cost: $${BASELINE.baseCostPerUnit}/unit. Overtime allocation: $${overtimeCost.toFixed(2)}/unit.`,
        data: { "Base Cost": `$${BASELINE.baseCostPerUnit}`, "OT Alloc": `$${overtimeCost.toFixed(2)}`, "Total Cost": `$${totalCost.toFixed(2)}` },
      },
      {
        kind: "tool_result",
        label: "margin_analysis",
        detail: `Margin at $${price.toFixed(2)}/unit: ${(margin * 100).toFixed(1)}%. Floor: ${(BASELINE.marginFloor * 100)}%. ${belowFloor ? "BELOW FLOOR." : "Above floor."}`,
        data: { "Margin": `${(margin * 100).toFixed(1)}%`, "Floor": `${(BASELINE.marginFloor * 100)}%`, "Status": belowFloor ? "VIOLATION" : "OK" },
      },
      ...(belowFloor ? [
        {
          kind: "tool_call" as const,
          label: "calculate_rush_surcharge(rate=" + (BASELINE.rushSurchargeRate * 100) + "%)",
          detail: `Margin below floor. Calculating ${(BASELINE.rushSurchargeRate * 100)}% rush surcharge to reach target.`,
        },
        {
          kind: "tool_result" as const,
          label: "surcharge_proposal",
          detail: `Proposed price: $${(price * (1 + BASELINE.rushSurchargeRate)).toFixed(2)}/unit. New margin: ${(((price * (1 + BASELINE.rushSurchargeRate)) - totalCost) / (price * (1 + BASELINE.rushSurchargeRate)) * 100).toFixed(1)}%.`,
          data: { "Proposed": `$${(price * (1 + BASELINE.rushSurchargeRate)).toFixed(2)}`, "New Margin": `${(((price * (1 + BASELINE.rushSurchargeRate)) - totalCost) / (price * (1 + BASELINE.rushSurchargeRate)) * 100).toFixed(1)}%` },
        },
        {
          kind: "objection" as const,
          label: "margin_floor_violation",
          detail: `OBJECTION: Margin ${(margin * 100).toFixed(1)}% below ${(BASELINE.marginFloor * 100)}% floor. Rush surcharge of ${(BASELINE.rushSurchargeRate * 100)}% required.`,
        },
      ] : [
        {
          kind: "agreement" as const,
          label: "margin_acceptable",
          detail: `Margin ${(margin * 100).toFixed(1)}% meets the ${(BASELINE.marginFloor * 100)}% floor. Price acceptable.`,
        },
      ]),
    ]

    return {
      agentId: "finance", round,
      status: belowFloor ? "objecting" : "agreed",
      reasoning: belowFloor
        ? `MARGIN ALERT: ${(margin * 100).toFixed(1)}% below ${(BASELINE.marginFloor * 100)}% floor. Requesting ${(BASELINE.rushSurchargeRate * 100)}% surcharge.`
        : `Margin ${(margin * 100).toFixed(1)}% meets floor.`,
      metrics: { "Price": `$${price.toFixed(2)}`, "Cost": `$${totalCost.toFixed(2)}`, "Margin": `${(margin * 100).toFixed(1)}%`, "Status": belowFloor ? "BELOW FLOOR" : "OK" },
      approved: !belowFloor,
      actions,
    }
  }

  if (round === 2) {
    const newPrice = price * (1 + BASELINE.rushSurchargeRate)
    const negotiatedPrice = Number(((newPrice + price) / 2 + 0.30).toFixed(2))
    const newMargin = (negotiatedPrice - totalCost) / negotiatedPrice
    const actions: ActionStep[] = [
      {
        kind: "tool_call",
        label: "negotiate_price(initial=$" + newPrice.toFixed(2) + ")",
        detail: `Opening negotiation with Sales. Initial position: $${newPrice.toFixed(2)}/unit (full surcharge).`,
      },
      {
        kind: "thinking",
        label: "evaluating_counter_offer",
        detail: `Sales counter: $${price.toFixed(2)} (no change). Strategic account concern. Evaluating split-the-difference approach.`,
      },
      {
        kind: "tool_call",
        label: "compute_compromise(offer=$" + negotiatedPrice.toFixed(2) + ")",
        detail: `Testing $${negotiatedPrice.toFixed(2)}/unit -- midpoint plus $0.30 buffer.`,
        data: { "Compromise": `$${negotiatedPrice.toFixed(2)}`, "Margin": `${(newMargin * 100).toFixed(1)}%` },
      },
      {
        kind: "tool_result",
        label: "compromise_analysis",
        detail: `$${negotiatedPrice.toFixed(2)}/unit yields ${(newMargin * 100).toFixed(1)}% margin. ${newMargin >= BASELINE.marginFloor ? "Above" : "Below"} floor.`,
        data: { "New Margin": `${(newMargin * 100).toFixed(1)}%`, "vs Floor": newMargin >= BASELINE.marginFloor ? "PASS" : "FAIL" },
      },
      {
        kind: "response",
        label: "price_negotiated",
        detail: `Accepting compromise at $${negotiatedPrice.toFixed(2)}/unit. Margin ${(newMargin * 100).toFixed(1)}% is tight but above floor.`,
      },
    ]

    return {
      agentId: "finance", round,
      status: "proposing",
      reasoning: `Negotiated from $${newPrice.toFixed(2)} to $${negotiatedPrice.toFixed(2)}/unit. Margin: ${(newMargin * 100).toFixed(1)}%.`,
      metrics: { "Proposed": `$${negotiatedPrice.toFixed(2)}`, "Margin": `${(newMargin * 100).toFixed(1)}%`, "Surcharge": "Partial" },
      approved: newMargin >= BASELINE.marginFloor,
      actions,
    }
  }

  const finalPrice = previousRound?.price ?? 10.80
  const finalMargin = (finalPrice - totalCost) / finalPrice
  const actions: ActionStep[] = [
    {
      kind: "tool_call",
      label: "verify_final_margin(price=$" + finalPrice.toFixed(2) + ")",
      detail: `Final margin verification at locked price.`,
    },
    {
      kind: "tool_result",
      label: "final_verification",
      detail: `Price: $${finalPrice.toFixed(2)}/unit. Margin: ${(finalMargin * 100).toFixed(1)}%. Floor: ${(BASELINE.marginFloor * 100)}%. PASS.`,
      data: { "Final Price": `$${finalPrice.toFixed(2)}`, "Final Margin": `${(finalMargin * 100).toFixed(1)}%`, "Status": "PASS" },
    },
    {
      kind: "agreement",
      label: "financial_approval_granted",
      detail: `Financial approval GRANTED. All margin thresholds met.`,
    },
  ]

  return {
    agentId: "finance", round,
    status: "agreed",
    reasoning: `Final price $${finalPrice.toFixed(2)}/unit locked. Margin ${(finalMargin * 100).toFixed(1)}% exceeds floor. Approved.`,
    metrics: { "Price": `$${finalPrice.toFixed(2)}`, "Margin": `${(finalMargin * 100).toFixed(1)}%`, "Approval": "GRANTED" },
    approved: true,
    actions,
  }
}

// ─── Logistics Agent ─────────────────────────────────────────────────────
export function logisticsAgent({ order, round, previousRound }: AgentInput): AgentProposal {
  const deliveryDays = previousRound?.deliveryDays ?? order.requestedDeliveryDays

  const evaluateMode = (days: number): { mode: ShippingMode; cost: number; transitDays: number } => {
    if (days <= 15) return { mode: "air", cost: BASELINE.airCostPerUnit, transitDays: BASELINE.airShippingDays }
    if (days <= 18) return { mode: "express", cost: BASELINE.expressCostPerUnit, transitDays: BASELINE.expressShippingDays }
    return { mode: "ground", cost: BASELINE.groundCostPerUnit, transitDays: BASELINE.groundShippingDays }
  }

  const { mode, cost, transitDays } = evaluateMode(deliveryDays)
  const totalShippingCost = cost * order.quantity

  if (round === 1) {
    const actions: ActionStep[] = [
      {
        kind: "tool_call",
        label: "evaluate_shipping_modes(days=" + deliveryDays + ")",
        detail: `Evaluating ground ($${BASELINE.groundCostPerUnit}/u, ${BASELINE.groundShippingDays}d), express ($${BASELINE.expressCostPerUnit}/u, ${BASELINE.expressShippingDays}d), air ($${BASELINE.airCostPerUnit}/u, ${BASELINE.airShippingDays}d).`,
        data: { "Ground": `$${BASELINE.groundCostPerUnit}/${BASELINE.groundShippingDays}d`, "Express": `$${BASELINE.expressCostPerUnit}/${BASELINE.expressShippingDays}d`, "Air": `$${BASELINE.airCostPerUnit}/${BASELINE.airShippingDays}d` },
      },
      {
        kind: "tool_result",
        label: "optimal_mode: " + mode,
        detail: `${mode.charAt(0).toUpperCase() + mode.slice(1)} freight optimal for ${deliveryDays}-day delivery. Transit: ${transitDays} days at $${cost.toFixed(2)}/unit.`,
        data: { "Mode": mode.toUpperCase(), "Transit": `${transitDays}d`, "Cost/Unit": `$${cost.toFixed(2)}`, "Total": `$${totalShippingCost.toLocaleString()}` },
      },
      {
        kind: "tool_call",
        label: "check_route_clearance(origin='Factory', dest='" + order.customer + "')",
        detail: `Checking carrier availability and route clearance for ${order.quantity} units via ${mode} freight.`,
      },
      {
        kind: "tool_result",
        label: "route_status: CLEAR",
        detail: `Route clearance: standard. No delays expected. Carrier capacity confirmed for ${order.quantity} units.`,
      },
      {
        kind: "response",
        label: "logistics_plan_ready",
        detail: `${mode.charAt(0).toUpperCase() + mode.slice(1)} freight, ${transitDays}-day transit, $${totalShippingCost.toLocaleString()} total shipping.`,
      },
    ]

    return {
      agentId: "logistics", round,
      status: "proposing",
      reasoning: `${mode.charAt(0).toUpperCase() + mode.slice(1)} freight: ${transitDays}-day transit at $${cost.toFixed(2)}/unit.`,
      metrics: { "Mode": mode.charAt(0).toUpperCase() + mode.slice(1), "Transit": `${transitDays}d`, "Cost/Unit": `$${cost.toFixed(2)}`, "Total": `$${totalShippingCost.toLocaleString()}` },
      approved: true,
      actions,
    }
  }

  const adjustedDays = previousRound?.deliveryDays ?? deliveryDays
  const adjusted = evaluateMode(adjustedDays)

  const actions: ActionStep[] = round === 2 ? [
    {
      kind: "tool_call",
      label: "re_evaluate_mode(delivery=" + adjustedDays + "d)",
      detail: `Production adjusted to ${adjustedDays}-day delivery. Re-checking shipping mode.`,
    },
    {
      kind: "tool_result",
      label: "mode_unchanged: " + adjusted.mode,
      detail: `${adjusted.mode.charAt(0).toUpperCase() + adjusted.mode.slice(1)} freight still optimal. No mode change needed. Transit: ${adjusted.transitDays}d.`,
      data: { "Mode": adjusted.mode.toUpperCase(), "Transit": `${adjusted.transitDays}d` },
    },
    {
      kind: "agreement",
      label: "logistics_confirmed",
      detail: `${adjustedDays}-day delivery works with ${adjusted.mode} freight. No changes required.`,
    },
  ] : [
    {
      kind: "tool_call",
      label: "book_carrier(mode='" + adjusted.mode + "')",
      detail: `Booking carrier for ${adjusted.mode} freight. Locking route and transit schedule.`,
    },
    {
      kind: "tool_result",
      label: "carrier_booked",
      detail: `Carrier confirmed. Route locked. Delivery by day ${adjustedDays} guaranteed.`,
      data: { "Carrier": "BOOKED", "Route": "LOCKED", "ETA": `Day ${adjustedDays}` },
    },
    {
      kind: "agreement",
      label: "logistics_locked",
      detail: `All logistics finalized. ${adjusted.mode.charAt(0).toUpperCase() + adjusted.mode.slice(1)} freight, day ${adjustedDays} delivery confirmed.`,
    },
  ]

  return {
    agentId: "logistics", round,
    status: round === 3 ? "agreed" : "proposing",
    reasoning: round === 2
      ? `${adjusted.mode.charAt(0).toUpperCase() + adjusted.mode.slice(1)} freight, ${adjusted.transitDays}d transit. No change needed.`
      : `Carrier booked. ${adjusted.mode.charAt(0).toUpperCase() + adjusted.mode.slice(1)} freight, day ${adjustedDays} delivery locked.`,
    metrics: { "Mode": adjusted.mode.charAt(0).toUpperCase() + adjusted.mode.slice(1), "Transit": `${adjusted.transitDays}d`, "Delivery": `Day ${adjustedDays}`, "Status": round === 3 ? "LOCKED" : "Planned" },
    approved: true,
    actions,
  }
}

// ─── Procurement Agent ───────────────────────────────────────────────────
export function procurementAgent({ order, round, previousRound }: AgentInput): AgentProposal {
  const deliveryDays = previousRound?.deliveryDays ?? order.requestedDeliveryDays
  const primaryViable = BASELINE.primaryLeadTimeDays <= deliveryDays - 5

  if (round === 1) {
    const actions: ActionStep[] = [
      {
        kind: "tool_call",
        label: "query_supplier_inventory(supplier='" + BASELINE.primarySupplier + "')",
        detail: `Checking ${BASELINE.primarySupplier} for ${order.quantity} units of raw materials. Lead time: ${BASELINE.primaryLeadTimeDays}d.`,
        data: { "Supplier": BASELINE.primarySupplier, "Lead Time": `${BASELINE.primaryLeadTimeDays}d`, "Cost": `$${BASELINE.materialCostPerUnit}/unit` },
      },
      {
        kind: "tool_result",
        label: primaryViable ? "supplier_available" : "supplier_tight",
        detail: primaryViable
          ? `${BASELINE.primarySupplier} confirmed. ${order.quantity} units available. Lead: ${BASELINE.primaryLeadTimeDays}d, cost: $${BASELINE.materialCostPerUnit}/unit.`
          : `${BASELINE.primarySupplier} lead time (${BASELINE.primaryLeadTimeDays}d) tight for ${deliveryDays}-day delivery.`,
        data: { "Available": primaryViable ? "YES" : "TIGHT", "Quantity": `${order.quantity}`, "Cost": `$${BASELINE.materialCostPerUnit}/unit` },
      },
      ...(!primaryViable ? [{
        kind: "tool_call" as const,
        label: `query_alternate_supplier(supplier='${BASELINE.alternateSupplier}')`,
        detail: `Checking alternate: ${BASELINE.alternateSupplier}. Lead: ${BASELINE.alternateLeadTimeDays}d, cost: $${BASELINE.alternateMaterialCostPerUnit}/unit.`,
      }] : []),
      {
        kind: primaryViable ? "agreement" : "response",
        label: primaryViable ? "procurement_confirmed" : "evaluating_options",
        detail: primaryViable
          ? `Materials confirmed with ${BASELINE.primarySupplier}. Ready for PO.`
          : `Evaluating ${BASELINE.primarySupplier} vs ${BASELINE.alternateSupplier}.`,
      },
    ]

    return {
      agentId: "procurement", round,
      status: primaryViable ? "agreed" : "proposing",
      reasoning: primaryViable
        ? `${BASELINE.primarySupplier} confirmed. Lead: ${BASELINE.primaryLeadTimeDays}d, $${BASELINE.materialCostPerUnit}/unit.`
        : `Primary lead time tight. Evaluating alternate supplier.`,
      metrics: { "Supplier": primaryViable ? BASELINE.primarySupplier : "Evaluating", "Lead": `${BASELINE.primaryLeadTimeDays}d`, "Cost": `$${BASELINE.materialCostPerUnit}/u` },
      approved: primaryViable,
      actions,
    }
  }

  const actions: ActionStep[] = round === 2 ? [
    {
      kind: "tool_call",
      label: "reserve_materials(qty=" + order.quantity + ")",
      detail: `Reserving ${order.quantity} units of raw materials with ${BASELINE.primarySupplier}.`,
    },
    {
      kind: "tool_result",
      label: "materials_reserved",
      detail: `Materials reserved. ${order.quantity} units locked at $${BASELINE.materialCostPerUnit}/unit. Total: $${(BASELINE.materialCostPerUnit * order.quantity).toLocaleString()}.`,
      data: { "Reserved": `${order.quantity}`, "Total": `$${(BASELINE.materialCostPerUnit * order.quantity).toLocaleString()}`, "Status": "RESERVED" },
    },
    {
      kind: "response",
      label: "purchase_order_ready",
      detail: `PO ready for execution. Awaiting final consensus to submit.`,
    },
  ] : [
    {
      kind: "tool_call",
      label: "submit_purchase_order()",
      detail: `Submitting PO to ${BASELINE.primarySupplier} for ${order.quantity} units.`,
    },
    {
      kind: "tool_result",
      label: "po_queued",
      detail: `PO #PO-${order.id} queued for execution. ${BASELINE.primarySupplier}, ${BASELINE.primaryLeadTimeDays}d lead, $${BASELINE.materialCostPerUnit}/unit.`,
      data: { "PO": `PO-${order.id}`, "Status": "QUEUED", "Supplier": BASELINE.primarySupplier },
    },
    {
      kind: "agreement",
      label: "procurement_locked",
      detail: `Procurement finalized. All materials sourced and PO queued.`,
    },
  ]

  return {
    agentId: "procurement", round,
    status: round === 3 ? "agreed" : "proposing",
    reasoning: round === 2
      ? `Materials reserved with ${BASELINE.primarySupplier}. PO ready.`
      : `PO queued. ${BASELINE.primarySupplier}, $${BASELINE.materialCostPerUnit}/unit.`,
    metrics: { "Supplier": BASELINE.primarySupplier, "Lead": `${BASELINE.primaryLeadTimeDays}d`, "Cost": `$${BASELINE.materialCostPerUnit}/u`, "Status": round === 3 ? "PO Queued" : "Reserved" },
    approved: true,
    actions,
  }
}

// ─── Sales Agent ─────────────────────────────────────────────────────────
export function salesAgent({ order, round, previousRound }: AgentInput): AgentProposal {
  if (round === 1) {
    const actions: ActionStep[] = [
      {
        kind: "tool_call",
        label: "lookup_customer_profile('" + order.customer + "')",
        detail: `Pulling CRM data for ${order.customer}. Checking tier, history, and relationship context.`,
      },
      {
        kind: "tool_result",
        label: "customer_profile",
        detail: `${order.customer}: ${BASELINE.customerTier} tier. ${BASELINE.relationshipYears}-year relationship. ${BASELINE.annualVolume.toLocaleString()} annual units. High-value account.`,
        data: { "Tier": BASELINE.customerTier, "Years": BASELINE.relationshipYears, "Annual Vol": `${BASELINE.annualVolume.toLocaleString()}` },
      },
      {
        kind: "tool_call",
        label: "check_delivery_flexibility()",
        detail: `Checking customer's acceptable delivery buffer based on historical orders.`,
      },
      {
        kind: "tool_result",
        label: "flexibility_analysis",
        detail: `Customer accepts +${BASELINE.acceptableDeliveryBuffer} day buffer based on past rush orders. Q3 launch deadline provides some slack.`,
        data: { "Buffer": `+${BASELINE.acceptableDeliveryBuffer}d`, "Deadline": "Q3 Launch" },
      },
      {
        kind: "response",
        label: "recommendation",
        detail: `Strategic account -- recommend accommodating with minimal price impact. ${BASELINE.acceptableDeliveryBuffer}-day buffer acceptable.`,
      },
    ]

    return {
      agentId: "sales", round,
      status: "proposing",
      reasoning: `${order.customer}: ${BASELINE.customerTier} tier, ${BASELINE.relationshipYears}yr, ${BASELINE.annualVolume.toLocaleString()} annual units. Recommend accommodating.`,
      metrics: { "Tier": BASELINE.customerTier, "Years": `${BASELINE.relationshipYears}`, "Volume": `${BASELINE.annualVolume.toLocaleString()}`, "Buffer": `+${BASELINE.acceptableDeliveryBuffer}d` },
      approved: true,
      actions,
    }
  }

  if (round === 2) {
    const proposedPrice = previousRound?.price ?? 10.80
    const actions: ActionStep[] = [
      {
        kind: "thinking",
        label: "evaluating_finance_proposal",
        detail: `Finance wants $${(order.requestedPrice * (1 + BASELINE.rushSurchargeRate)).toFixed(2)}/unit (full surcharge). This is too aggressive for a strategic account.`,
      },
      {
        kind: "tool_call",
        label: "calculate_counter_offer()",
        detail: `Computing counter-offer that balances margin needs with customer retention.`,
      },
      {
        kind: "tool_result",
        label: "counter_proposal",
        detail: `Counter: $${proposedPrice.toFixed(2)}/unit. Splits difference. Customer relationship impact: minimal. Acceptable to customer per profile.`,
        data: { "Counter": `$${proposedPrice.toFixed(2)}`, "Impact": "Minimal", "Delivery": `${previousRound?.deliveryDays ?? 19}d` },
      },
      {
        kind: "response",
        label: "counter_submitted",
        detail: `Counter-proposed $${proposedPrice.toFixed(2)}/unit with ${previousRound?.deliveryDays ?? 19}-day delivery. Customer will accept +1 day buffer.`,
      },
    ]

    return {
      agentId: "sales", round,
      status: "proposing",
      reasoning: `Counter: $${proposedPrice.toFixed(2)}/unit, ${previousRound?.deliveryDays ?? 19}-day delivery. Customer impact minimal.`,
      metrics: { "Price": `$${proposedPrice.toFixed(2)}`, "Delivery": `${previousRound?.deliveryDays ?? 19}d`, "Impact": "Minimal" },
      approved: true,
      actions,
    }
  }

  const finalPrice = previousRound?.price ?? 10.80
  const dealValue = finalPrice * order.quantity
  const actions: ActionStep[] = [
    {
      kind: "tool_call",
      label: "calculate_deal_value()",
      detail: `Computing final deal metrics for ${order.customer}.`,
      data: { "Price": `$${finalPrice.toFixed(2)}`, "Qty": `${order.quantity}`, "Value": `$${dealValue.toLocaleString()}` },
    },
    {
      kind: "tool_result",
      label: "deal_summary",
      detail: `Deal value: $${dealValue.toLocaleString()}. Terms: $${finalPrice.toFixed(2)}/unit, ${previousRound?.deliveryDays ?? 19}-day delivery. Customer satisfaction: HIGH.`,
      data: { "Deal Value": `$${dealValue.toLocaleString()}`, "Satisfaction": "HIGH" },
    },
    {
      kind: "agreement",
      label: "sales_approved",
      detail: `Terms finalized. Customer relationship preserved. Deal approved.`,
    },
  ]

  return {
    agentId: "sales", round,
    status: "agreed",
    reasoning: `$${finalPrice.toFixed(2)}/unit, ${previousRound?.deliveryDays ?? 19}d. Deal value: $${dealValue.toLocaleString()}.`,
    metrics: { "Price": `$${finalPrice.toFixed(2)}`, "Value": `$${dealValue.toLocaleString()}`, "Satisfaction": "High", "Approval": "GRANTED" },
    approved: true,
    actions,
  }
}
