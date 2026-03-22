import { NextResponse } from "next/server"
import type { Order, RoundSummary } from "@/lib/synk/types"
import { runRound } from "@/lib/synk/orchestrator"

// POST /api/rounds — Execute a single negotiation round with all agents
// Body: { order: Order, round: number, previousRound?: RoundSummary }
export async function POST(request: Request) {
  const body = await request.json()

  if (!body.order) {
    return NextResponse.json({ error: "Missing 'order' in request body" }, { status: 400 })
  }

  const order: Order = body.order
  const round: number = body.round ?? 1
  const previousRound: RoundSummary | undefined = body.previousRound

  if (round < 1 || round > 3) {
    return NextResponse.json({ error: "Round must be between 1 and 3" }, { status: 400 })
  }

  const roundSummary = runRound(order, round, previousRound)

  return NextResponse.json({
    round: roundSummary.round,
    converged: roundSummary.converged,
    summary: roundSummary,
    agentProposals: roundSummary.proposals.map(p => ({
      agentId: p.agentId,
      status: p.status,
      approved: p.approved,
      reasoning: p.reasoning,
      metrics: p.metrics,
      actions: p.actions,
    })),
  })
}
