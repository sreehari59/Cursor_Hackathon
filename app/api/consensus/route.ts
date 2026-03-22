import { NextResponse } from "next/server"
import type { Order, RoundSummary } from "@/lib/synk/types"
import { synthesizeConsensus } from "@/lib/synk/orchestrator"

// POST /api/consensus — Synthesize consensus from completed negotiation rounds
// Body: { order: Order, rounds: RoundSummary[] }
export async function POST(request: Request) {
  const body = await request.json()

  if (!body.order || !body.rounds) {
    return NextResponse.json({ error: "Missing 'order' or 'rounds' in request body" }, { status: 400 })
  }

  const order: Order = body.order
  const rounds: RoundSummary[] = body.rounds

  if (rounds.length === 0) {
    return NextResponse.json({ error: "At least one round is required to synthesize consensus" }, { status: 400 })
  }

  const consensus = synthesizeConsensus(rounds, order)

  return NextResponse.json({
    consensus,
    metadata: {
      totalRounds: rounds.length,
      finalRound: rounds[rounds.length - 1].round,
      allConverged: rounds[rounds.length - 1].converged,
      agentApprovals: rounds[rounds.length - 1].proposals.map(p => ({
        agentId: p.agentId,
        approved: p.approved,
        status: p.status,
      })),
    },
  })
}
