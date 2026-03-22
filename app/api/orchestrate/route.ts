import type { Order, SSEEvent, DemoPhase, AgentId, AgentMessage } from "@/lib/synk/types"
import { runRound, synthesizeConsensus } from "@/lib/synk/orchestrator"
import { VOICE_SCRIPT } from "@/lib/synk/scenario"

const AGENT_ORDER: AgentId[] = ["production", "finance", "logistics", "procurement", "sales"]

function encode(event: SSEEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`
}

let msgId = 0
function makeMsg(
  from: AgentId | "orchestrator",
  to: AgentId | "orchestrator" | "all",
  round: number,
  type: AgentMessage["type"],
  message: string
): AgentMessage {
  return { id: `msg-${++msgId}`, from, to, round, type, message, timestamp: Date.now() }
}

// Pre-scripted inter-agent dialogue per round
function getRoundMessages(round: number): AgentMessage[] {
  if (round === 1) {
    return [
      makeMsg("orchestrator", "all", 1, "directive", "Broadcasting rush order ORD-RUSH-001 to all agents. Begin independent analysis."),
      makeMsg("production", "orchestrator", 1, "proposal", "Capacity check: need 7 production days but only have 13 available. Overtime of 12h required. Feasible with adjustments."),
      makeMsg("finance", "orchestrator", 1, "objection", "MARGIN ALERT: At $10.00/unit, margin is 12.4% -- BELOW the 15% floor. Requesting rush surcharge of 12%."),
      makeMsg("logistics", "orchestrator", 1, "proposal", "Ground freight selected for 18-day delivery: 5-day transit, $0.30/unit. Route clearance standard."),
      makeMsg("procurement", "orchestrator", 1, "info", "Primary supplier ChemCorp Asia confirmed. 10-day lead time, materials available for 5,000 units."),
      makeMsg("sales", "orchestrator", 1, "proposal", "Acme Corp is a Strategic account (5yr, 120K annual units). Recommend accommodating with minimal price impact. +2 day buffer acceptable."),
      makeMsg("orchestrator", "all", 1, "directive", "Round 1 complete. Finance has flagged margin below floor. Initiating cross-agent negotiation."),
    ]
  }
  if (round === 2) {
    return [
      makeMsg("orchestrator", "all", 2, "directive", "Round 2: Finance and Sales must negotiate price. Production to re-evaluate with adjusted timeline."),
      makeMsg("finance", "sales", 2, "proposal", "Proposing $11.20/unit with 12% rush surcharge to meet margin floor."),
      makeMsg("sales", "finance", 2, "objection", "Too aggressive for a strategic account. Counter: $10.80/unit -- splits the difference, preserves relationship."),
      makeMsg("finance", "sales", 2, "counter", "Reviewing $10.80... margin at 17.2%. Above 15% floor. Acceptable -- but tight."),
      makeMsg("production", "logistics", 2, "info", "Adjusting to 19-day delivery. Overtime reduced from 12h to 8h. Schedule feasible."),
      makeMsg("logistics", "production", 2, "agreement", "19-day delivery works. Ground freight still optimal. No mode change needed."),
      makeMsg("procurement", "orchestrator", 2, "agreement", "Materials reserved with ChemCorp Asia. Purchase order ready for execution."),
      makeMsg("orchestrator", "all", 2, "directive", "Price negotiated to $10.80. Delivery adjusted to 19 days. Round 2 converging."),
    ]
  }
  // Round 3
  return [
    makeMsg("orchestrator", "all", 3, "directive", "Round 3: Final verification. All agents confirm or raise final objections."),
    makeMsg("production", "orchestrator", 3, "agreement", "Production schedule locked. 19-day delivery, 8h overtime confirmed. No objections."),
    makeMsg("finance", "orchestrator", 3, "agreement", "Final price $10.80/unit locked. Margin 17.2% exceeds floor. Financial approval GRANTED."),
    makeMsg("logistics", "orchestrator", 3, "agreement", "Ground freight confirmed. Carrier booked, route locked. Delivery by day 19 confirmed."),
    makeMsg("procurement", "orchestrator", 3, "agreement", "ChemCorp Asia locked. 10-day lead, $3.20/unit. PO queued for execution."),
    makeMsg("sales", "orchestrator", 3, "agreement", "Terms finalized. $10.80/unit, 19-day delivery. Customer relationship preserved. Deal value: $54,000."),
    makeMsg("orchestrator", "all", 3, "directive", "CONSENSUS REACHED. All 5 agents approved. Confidence: 94%. Proceeding to customer callback."),
  ]
}

function buildFallbackStream(order: Order, backendMessage?: string) {
  return new ReadableStream({
    async start(controller) {
      const send = (event: SSEEvent) => {
        controller.enqueue(new TextEncoder().encode(encode(event)))
      }

      const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

      try {
        send({
          type: "backend_status",
          data: {
            backendSource: "frontend-fallback",
            backendMessage: backendMessage || "Backend unavailable. Showing frontend dummy data.",
          },
        })

        // Phase: Order Broadcast
        send({ type: "phase_change", data: { phase: "order-broadcast" as DemoPhase } })
        await delay(1200)

        // Run 3 negotiation rounds
        const rounds: ReturnType<typeof runRound>[] = []
        for (let round = 1; round <= 3; round++) {
          const phase = `round-${round}` as DemoPhase
          send({ type: "phase_change", data: { phase } })
          await delay(500)

          const previousRound = rounds.length > 0 ? rounds[rounds.length - 1] : undefined

          let roundResult: ReturnType<typeof runRound>
          try {
            roundResult = runRound(order, round, previousRound)
          } catch (err) {
            console.error(`[v0] runRound(${round}) error:`, err)
            // Send a fallback so stream doesn't die
            send({ type: "phase_change", data: { phase: "done" as DemoPhase } })
            send({ type: "done", data: {} })
            controller.close()
            return
          }
          rounds.push(roundResult)

          // Send inter-agent messages with staggered timing
          const messages = getRoundMessages(round)
          for (const agentMsg of messages) {
            send({ type: "agent_message", data: { agentMessage: agentMsg } })
            await delay(600)
          }

          // Stream each agent's proposal
          for (const proposal of roundResult.proposals) {
            send({
              type: "agent_update",
              data: { agentId: proposal.agentId, proposal },
            })
            const stepCount = proposal.actions?.length || 2
            await delay(400 + stepCount * 150)
          }

          send({
            type: "round_complete",
            data: { roundSummary: roundResult },
          })
          await delay(600)
        }

        // Consensus
        send({ type: "phase_change", data: { phase: "consensus" as DemoPhase } })
        await delay(800)

        const consensus = synthesizeConsensus(rounds, order)
        send({ type: "consensus_reached", data: { consensus } })
        await delay(1500)

        // Callback
        send({ type: "phase_change", data: { phase: "callback" as DemoPhase } })
        send({ type: "callback_start", data: { message: `Calling back ${order.customer}...` } })
        await delay(1500)

        const callbackMessages = consensus.approved
          ? VOICE_SCRIPT.callbackMessages
          : VOICE_SCRIPT.callbackMessagesRejected

        for (const msg of callbackMessages) {
          send({ type: "callback_message", data: { message: msg } })
          await delay(1000)
        }

        await delay(500)
        send({ type: "phase_change", data: { phase: "done" as DemoPhase } })
        send({ type: "done", data: {} })
      } catch (err) {
        console.error("[v0] fallback SSE stream error:", err)
      } finally {
        controller.close()
      }
    },
  })
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const orderJson = searchParams.get("order")

  if (!orderJson) {
    return new Response("Missing order parameter", { status: 400 })
  }

  const order: Order = JSON.parse(decodeURIComponent(orderJson))
  msgId = 0

  const backendBase = (process.env.BACKEND_API_BASE_URL || "http://localhost:5000/api").replace(/\/$/, "")
  const backendUrl = `${backendBase}/orchestrate?order=${encodeURIComponent(JSON.stringify(order))}`

  try {
    const backendResponse = await fetch(backendUrl, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
      cache: "no-store",
    })

    if (!backendResponse.ok || !backendResponse.body) {
      throw new Error(`Backend returned ${backendResponse.status}`)
    }

    const backendStream = new ReadableStream({
      async start(controller) {
        controller.enqueue(
          new TextEncoder().encode(
            encode({
              type: "backend_status",
              data: {
                backendSource: "backend",
                backendMessage: `Connected to ${backendBase}`,
              },
            })
          )
        )

        const reader = backendResponse.body!.getReader()
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            if (value) controller.enqueue(value)
          }
        } catch (err) {
          console.error("[v0] backend SSE proxy error:", err)
        } finally {
          controller.close()
          reader.releaseLock()
        }
      },
    })

    return new Response(backendStream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    })
  } catch (err) {
    const message = err instanceof Error
      ? `Backend unreachable (${backendBase}): ${err.message}. Showing frontend dummy data.`
      : `Backend unreachable (${backendBase}). Showing frontend dummy data.`
    console.warn("[v0] falling back to frontend orchestration:", message)

    const fallbackStream = buildFallbackStream(order, message)
    return new Response(fallbackStream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    })
  }
}
