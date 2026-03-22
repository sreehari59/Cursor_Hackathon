// ─── SYNK Orchestrator ───────────────────────────────────────────────────
import type { Order, RoundSummary, ConsensusResult, AgentProposal, ShippingMode } from "./types"
import { productionAgent, financeAgent, logisticsAgent, procurementAgent, salesAgent } from "./agents"

export function runRound(order: Order, round: number, previousRound?: RoundSummary): RoundSummary {
  const input = { order, round, previousRound }

  const proposals: AgentProposal[] = [
    productionAgent(input),
    financeAgent(input),
    logisticsAgent(input),
    procurementAgent(input),
    salesAgent(input),
  ]

  // Calculate round parameters based on proposals
  let price = previousRound?.price ?? order.requestedPrice
  let deliveryDays = previousRound?.deliveryDays ?? order.requestedDeliveryDays
  let shippingMode: ShippingMode = previousRound?.shippingMode ?? "ground"
  let overtimeHours = previousRound?.overtimeHours ?? 0

  if (round === 1) {
    // Finance flags margin issue, production identifies overtime
    const financeProposal = proposals.find(p => p.agentId === "finance")!
    if (!financeProposal.approved) {
      price = order.requestedPrice * 1.12 // Rush surcharge proposed
    }
    const prodMetrics = proposals.find(p => p.agentId === "production")!.metrics
    // Parse overtime from "12h" format
    const otValue = String(prodMetrics["Overtime"] ?? "0")
    overtimeHours = parseInt(otValue.replace(/[^0-9]/g, ""), 10) || 0

    const logisticsProposal = proposals.find(p => p.agentId === "logistics")!
    // Key is "Mode" not "Shipping Mode"
    const modeStr = String(logisticsProposal.metrics["Mode"] ?? "ground").toLowerCase()
    shippingMode = (modeStr === "air" || modeStr === "express" || modeStr === "ground") ? modeStr : "ground"
  }

  if (round === 2) {
    // Sales negotiates price down, delivery adjusted +1 day
    price = 10.80
    deliveryDays = 19
    shippingMode = "ground"
    overtimeHours = 8
  }

  if (round === 3) {
    // Final stabilization
    price = 10.80
    deliveryDays = 19
    shippingMode = "ground"
    overtimeHours = 8
  }

  const totalCost = 8.50 + (overtimeHours * 45) / order.quantity
  const margin = (price - totalCost) / price
  const converged = round >= 2 && proposals.every(p => p.approved)

  return {
    round,
    price,
    deliveryDays,
    margin: Number((margin * 100).toFixed(1)),
    shippingMode,
    overtimeHours,
    proposals,
    converged,
  }
}

export function synthesizeConsensus(rounds: RoundSummary[], order: Order): ConsensusResult {
  const finalRound = rounds[rounds.length - 1]
  const approved = finalRound.converged && finalRound.margin >= 15

  return {
    approved,
    finalPrice: finalRound.price,
    finalDeliveryDays: finalRound.deliveryDays,
    finalMargin: finalRound.margin,
    shippingMode: finalRound.shippingMode,
    riskScore: finalRound.margin >= 18 ? "Low" : finalRound.margin >= 15 ? "Medium" : "High",
    confidence: approved ? 94 : 45,
    supplier: "ChemCorp Asia",
    overtimeHours: finalRound.overtimeHours,
    summary: approved
      ? `Order ${order.id} APPROVED. ${order.quantity} units of ${order.product} at $${finalRound.price.toFixed(2)}/unit, delivered in ${finalRound.deliveryDays} days via ${finalRound.shippingMode} freight. Margin: ${finalRound.margin}%. All agents reached consensus in ${rounds.length} rounds.`
      : `Order ${order.id} REJECTED. Unable to meet requested terms within operational constraints. Margin ${finalRound.margin}% below floor after ${rounds.length} negotiation rounds.`,
  }
}
