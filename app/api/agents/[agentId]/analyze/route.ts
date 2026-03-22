import { NextResponse } from "next/server"
import type { AgentId, Order, RoundSummary } from "@/lib/synk/types"
import { productionAgent, financeAgent, logisticsAgent, procurementAgent, salesAgent } from "@/lib/synk/agents"

// POST /api/agents/:agentId/analyze — Run a single agent's analysis on an order
// Body: { order: Order, round: number, previousRound?: RoundSummary }
export async function POST(
  request: Request,
  { params }: { params: Promise<{ agentId: string }> }
) {
  const { agentId } = await params
  const body = await request.json()

  const validAgents: AgentId[] = ["production", "finance", "logistics", "procurement", "sales"]
  if (!validAgents.includes(agentId as AgentId)) {
    return NextResponse.json({ error: `Invalid agent: ${agentId}` }, { status: 400 })
  }

  if (!body.order) {
    return NextResponse.json({ error: "Missing 'order' in request body" }, { status: 400 })
  }

  const order: Order = body.order
  const round: number = body.round ?? 1
  const previousRound: RoundSummary | undefined = body.previousRound

  const agentFn = {
    production: productionAgent,
    finance: financeAgent,
    logistics: logisticsAgent,
    procurement: procurementAgent,
    sales: salesAgent,
  }[agentId as AgentId]

  const proposal = agentFn({ order, round, previousRound })

  return NextResponse.json({
    agentId,
    round,
    proposal,
  })
}
