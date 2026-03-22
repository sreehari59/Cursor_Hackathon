"use client"

import { useCallback, useEffect, useReducer, useRef } from "react"
import type {
  AgentId,
  AgentMessage,
  AgentProposal,
  ConsensusResult,
  DemoPhase,
  Order,
  RoundSummary,
  SSEEvent,
} from "@/lib/synk/types"
import { DEFAULT_ORDER } from "@/lib/synk/scenario"
import { LiveAudioPlayer } from "@/lib/synk/live-audio"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { SynkHeader } from "@/components/synk/header"
import { VoiceAgentPanel } from "@/components/synk/voice-agent-panel"
import { OrchestrationPanel } from "@/components/synk/orchestration-panel"
import type { TranscriptMessage } from "@/components/synk/voice-transcript"

const EMPTY_ORDER: Order = {
  id: "",
  customer: "",
  product: "",
  quantity: 0,
  requestedPrice: 0,
  requestedDeliveryDays: 0,
  priority: "rush",
}

export interface CallLog {
  id: string
  customer: string
  product: string
  quantity: number
  outcome: "approved" | "rejected"
  finalPrice?: number
  timestamp: number
}

interface AppState {
  phase: DemoPhase
  backendSource: "unknown" | "backend" | "frontend-fallback"
  backendMessage: string | null
  voiceOrderReady: boolean
  voiceStatusMessage: string | null
  liveAudioListenUrl: string | null
  liveAudioStatus: string | null
  order: Order
  transcript: TranscriptMessage[]
  activeAgents: Set<AgentId>
  proposals: Map<AgentId, AgentProposal>
  allProposals: AgentProposal[]
  rounds: RoundSummary[]
  consensus: ConsensusResult | null
  agentMessages: AgentMessage[]
  msgCounter: number
  callHistory: CallLog[]
}

type Action =
  | { type: "SET_PHASE"; phase: DemoPhase }
  | { type: "SET_BACKEND_STATUS"; backendSource: "unknown" | "backend" | "frontend-fallback"; backendMessage?: string }
  | { type: "SET_VOICE_STATUS"; ready: boolean; message?: string | null }
  | { type: "SET_LIVE_AUDIO"; listenUrl?: string | null; status?: string | null }
  | { type: "SET_ORDER"; order: Order }
  | { type: "ADD_TRANSCRIPT"; msg: TranscriptMessage }
  | { type: "SET_ACTIVE_AGENTS"; agents: Set<AgentId> }
  | { type: "UPDATE_PROPOSAL"; proposal: AgentProposal }
  | { type: "ADD_ROUND"; round: RoundSummary }
  | { type: "SET_CONSENSUS"; consensus: ConsensusResult }
  | { type: "ADD_AGENT_MESSAGE"; agentMessage: AgentMessage }
  | { type: "CLEAR_PROPOSALS" }
  | { type: "SAVE_CALL_LOG"; log: CallLog }
  | { type: "RESET" }

const initialState: AppState = {
  phase: "idle",
  backendSource: "unknown",
  backendMessage: null,
  voiceOrderReady: false,
  voiceStatusMessage: null,
  liveAudioListenUrl: null,
  liveAudioStatus: null,
  order: { ...DEFAULT_ORDER },
  transcript: [],
  activeAgents: new Set(),
  proposals: new Map(),
  allProposals: [],
  rounds: [],
  consensus: null,
  agentMessages: [],
  msgCounter: 0,
  callHistory: [],
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_PHASE":
      return { ...state, phase: action.phase }
    case "SET_BACKEND_STATUS":
      return { ...state, backendSource: action.backendSource, backendMessage: action.backendMessage ?? null }
    case "SET_VOICE_STATUS":
      return { ...state, voiceOrderReady: action.ready, voiceStatusMessage: action.message ?? null }
    case "SET_LIVE_AUDIO":
      return {
        ...state,
        liveAudioListenUrl: action.listenUrl === undefined ? state.liveAudioListenUrl : action.listenUrl,
        liveAudioStatus: action.status === undefined ? state.liveAudioStatus : action.status,
      }
    case "SET_ORDER":
      return { ...state, order: action.order }
    case "ADD_TRANSCRIPT": {
      const newCounter = state.msgCounter + 1
      return {
        ...state,
        transcript: [...state.transcript, { ...action.msg, id: `msg-${newCounter}` }],
        msgCounter: newCounter,
      }
    }
    case "SET_ACTIVE_AGENTS":
      return { ...state, activeAgents: new Set(action.agents) }
    case "UPDATE_PROPOSAL": {
      const newProposals = new Map(state.proposals)
      newProposals.set(action.proposal.agentId, action.proposal)
      return {
        ...state,
        proposals: newProposals,
        allProposals: [...state.allProposals, action.proposal],
      }
    }
    case "ADD_ROUND":
      return { ...state, rounds: [...state.rounds, action.round] }
    case "SET_CONSENSUS":
      return { ...state, consensus: action.consensus }
    case "ADD_AGENT_MESSAGE":
      return { ...state, agentMessages: [...state.agentMessages, action.agentMessage] }
    case "CLEAR_PROPOSALS":
      return { ...state, proposals: new Map() }
    case "SAVE_CALL_LOG":
      return { ...state, callHistory: [action.log, ...state.callHistory] }
    case "RESET":
      return { ...initialState, order: { ...DEFAULT_ORDER }, callHistory: state.callHistory }
    default:
      return state
  }
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function normalizeCapturedOrder(rawOrder: Record<string, unknown>): Order {
  const priority = rawOrder.priority === "critical" ? "critical" : rawOrder.priority === "standard" ? "standard" : "rush"
  return {
    id: String(rawOrder.id ?? `ORD-VOICE-${Date.now()}`),
    customer: String(rawOrder.customer ?? "Voice Customer"),
    product: String(rawOrder.product ?? DEFAULT_ORDER.product),
    quantity: Number(rawOrder.quantity ?? DEFAULT_ORDER.quantity),
    requestedPrice: Number(rawOrder.requestedPrice ?? DEFAULT_ORDER.requestedPrice),
    requestedDeliveryDays: Number(rawOrder.requestedDeliveryDays ?? DEFAULT_ORDER.requestedDeliveryDays),
    priority,
  }
}

function extractReadyOrder(payload: unknown): Order | null {
  const voiceResult = payload && typeof payload === "object" ? (payload as { voiceResult?: { ready?: boolean; order?: Record<string, unknown> } }).voiceResult : undefined
  if (voiceResult?.ready && voiceResult?.order) {
    return normalizeCapturedOrder(voiceResult.order)
  }
  return null
}

function extractCallStatus(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null
  }
  const record = payload as {
    call?: { status?: unknown }
    voiceResult?: { lastCall?: { status?: unknown } }
  }
  const directStatus = record.call?.status
  if (typeof directStatus === "string" && directStatus) {
    return directStatus
  }
  const lastCallStatus = record.voiceResult?.lastCall?.status
  if (typeof lastCallStatus === "string" && lastCallStatus) {
    return lastCallStatus
  }
  return null
}

export default function SynkDemo() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const abortRef = useRef<AbortController | null>(null)
  const autoSubmitRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const currentOrderRef = useRef<Order>({ ...DEFAULT_ORDER })
  const liveAudioPlayerRef = useRef<LiveAudioPlayer | null>(null)

  const addTranscript = useCallback((sender: "customer" | "agent", text: string) => {
    dispatch({ type: "ADD_TRANSCRIPT", msg: { id: "", sender, text } })
  }, [])

  const clearAutoSubmit = useCallback(() => {
    if (autoSubmitRef.current) {
      clearTimeout(autoSubmitRef.current)
      autoSubmitRef.current = null
    }
  }, [])

  const stopLiveAudio = useCallback(() => {
    liveAudioPlayerRef.current?.stop()
    liveAudioPlayerRef.current = null
    dispatch({ type: "SET_LIVE_AUDIO", listenUrl: null, status: null })
  }, [])

  const startLiveAudio = useCallback(async (listenUrl: string | null | undefined, provider?: string | null) => {
    if (!listenUrl) {
      dispatch({ type: "SET_LIVE_AUDIO", listenUrl: null, status: "No live audio stream available." })
      return
    }

    const format = provider?.toLowerCase() === "twilio" ? "mulaw" : "pcm_s16le"
    stopLiveAudio()
    const player = new LiveAudioPlayer({
      format,
      sampleRate: format === "mulaw" ? 8000 : 16000,
      onStatus: (status) => {
        dispatch({
          type: "SET_LIVE_AUDIO",
          listenUrl,
          status: status === "live-audio-connected" ? "Live conversation audio connected." : "Live conversation audio stopped.",
        })
      },
      onError: (message) => {
        dispatch({ type: "SET_LIVE_AUDIO", listenUrl, status: message })
      },
    })
    liveAudioPlayerRef.current = player
    dispatch({ type: "SET_LIVE_AUDIO", listenUrl, status: "Connecting live conversation audio..." })
    try {
      await player.start(listenUrl)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to start live conversation audio."
      dispatch({ type: "SET_LIVE_AUDIO", listenUrl, status: message })
    }
  }, [stopLiveAudio])

  useEffect(() => {
    return () => {
      liveAudioPlayerRef.current?.stop()
    }
  }, [])

  const processSSEEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case "backend_status":
        if (event.data.backendSource) {
          dispatch({
            type: "SET_BACKEND_STATUS",
            backendSource: event.data.backendSource,
            backendMessage: event.data.backendMessage,
          })
          if (event.data.backendSource === "frontend-fallback") {
            addTranscript("agent", event.data.backendMessage || "Backend unavailable. Showing frontend dummy data.")
          }
        }
        break

      case "phase_change":
        if (event.data.phase) {
          dispatch({ type: "SET_PHASE", phase: event.data.phase })
        }
        break

      case "agent_update":
        if (event.data.proposal) {
          dispatch({ type: "UPDATE_PROPOSAL", proposal: event.data.proposal })
        }
        break

      case "agent_message":
        if (event.data.agentMessage) {
          dispatch({ type: "ADD_AGENT_MESSAGE", agentMessage: event.data.agentMessage })
        }
        break

      case "round_complete":
        if (event.data.roundSummary) {
          dispatch({ type: "ADD_ROUND", round: event.data.roundSummary })
        }
        break

      case "consensus_reached":
        if (event.data.consensus) {
          const currentOrder = currentOrderRef.current
          dispatch({ type: "SET_CONSENSUS", consensus: event.data.consensus })
          dispatch({
            type: "SAVE_CALL_LOG",
            log: {
              id: `call-${Date.now()}`,
              customer: currentOrder.customer,
              product: currentOrder.product,
              quantity: currentOrder.quantity,
              outcome: event.data.consensus.approved ? "approved" : "rejected",
              finalPrice: event.data.consensus.finalPrice,
              timestamp: Date.now(),
            },
          })
        }
        break

      case "callback_start":
        addTranscript("agent", "Calling back customer...")
        break

      case "callback_message":
        if (event.data.message) {
          addTranscript("agent", event.data.message)
        }
        break

      case "done":
        break
    }
  }, [addTranscript])

  const startOrderOrchestration = useCallback(async (orderToSubmit: Order) => {
    clearAutoSubmit()
    dispatch({ type: "SET_PHASE", phase: "order-broadcast" })

    const allAgents: AgentId[] = ["production", "finance", "logistics", "procurement", "sales"]
    dispatch({ type: "SET_ACTIVE_AGENTS", agents: new Set(allAgents) })

    abortRef.current = new AbortController()

    try {
      const orderParam = encodeURIComponent(JSON.stringify(orderToSubmit))
      const response = await fetch(`/api/orchestrate?order=${orderParam}`, {
        signal: abortRef.current.signal,
      })

      if (!response.body) {
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n\n")
        buffer = lines.pop() || ""

        for (const line of lines) {
          const dataLine = line.replace(/^data: /, "").trim()
          if (!dataLine) continue

          try {
            const event: SSEEvent = JSON.parse(dataLine)
            processSSEEvent(event)
          } catch {
            // Skip malformed events
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") {
        console.error("SSE stream error:", err)
      }
    }
  }, [clearAutoSubmit, processSSEEvent])

  const handleStartSystem = useCallback(async () => {
    dispatch({ type: "RESET" })
    currentOrderRef.current = { ...EMPTY_ORDER }
    clearAutoSubmit()
    stopLiveAudio()
    dispatch({ type: "SET_ORDER", order: { ...EMPTY_ORDER } })
    dispatch({ type: "SET_PHASE", phase: "active-call" })
    dispatch({
      type: "SET_VOICE_STATUS",
      ready: false,
      message: "Outbound voice call started. Waiting for structured order capture.",
    })
    addTranscript("agent", "Starting outbound voice system.")

    try {
      const startResponse = await fetch("/api/voice-agent/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      const startPayload = await startResponse.json().catch(() => null)
      if (!startResponse.ok) {
        throw new Error(startPayload?.message || "Voice agent start failed.")
      }

      const customerNumber = startPayload?.customerNumber
      const listenUrl = startPayload?.call?.monitor?.listenUrl
      const provider = startPayload?.call?.phoneCallProvider
      addTranscript(
        "agent",
        startPayload?.debugTag === "transcript-replay"
          ? `Transcript replay loaded from call ${startPayload?.call?.id || "configured replay source"}.`
          : customerNumber
            ? `Outbound call placed to ${customerNumber}. Waiting for order extraction.`
            : "Outbound call placed. Waiting for order extraction."
      )
      if (listenUrl && startPayload?.debugTag !== "transcript-replay") {
        addTranscript("agent", "Connecting live conversation audio monitor.")
        await startLiveAudio(listenUrl, provider)
      }

      const pollStartedAt = Date.now()
      const maxPollDurationMs = 180000
      let attempt = 0
      let endedWithoutOrderAttempts = 0

      while (Date.now() - pollStartedAt < maxPollDurationMs) {
        attempt += 1
        await delay(3000)
        const latestResponse = await fetch("/api/voice-agent/latest", { cache: "no-store" })
        const latestPayload = await latestResponse.json().catch(() => null)
        const voiceResult = latestPayload?.voiceResult
        let capturedOrder = extractReadyOrder(latestPayload)
        let transcriptPayload: unknown = null

        if (!capturedOrder && attempt >= 4) {
          const transcriptResponse = await fetch("/api/voice-agent/latest-transcript", { cache: "no-store" })
          transcriptPayload = await transcriptResponse.json().catch(() => null)
          capturedOrder = extractReadyOrder(transcriptPayload)
        }

        if (capturedOrder) {
          currentOrderRef.current = capturedOrder
          dispatch({ type: "SET_ORDER", order: capturedOrder })
          dispatch({
            type: "SET_VOICE_STATUS",
            ready: true,
            message: "Structured order captured. Auto-submitting in 20 seconds.",
          })
          addTranscript(
            "agent",
            `Captured order: ${capturedOrder.quantity} units of ${capturedOrder.product} at $${capturedOrder.requestedPrice.toFixed(2)} with ${capturedOrder.requestedDeliveryDays}-day delivery.`
          )
          addTranscript("agent", "Order is ready. Auto-submitting to the agent network in 20 seconds.")

          clearAutoSubmit()
          autoSubmitRef.current = setTimeout(() => {
            void startOrderOrchestration(capturedOrder)
          }, 20000)
          return
        }

        const callStatus = extractCallStatus(transcriptPayload) || extractCallStatus(latestPayload)
        if (callStatus === "ended") {
          endedWithoutOrderAttempts += 1
        } else {
          endedWithoutOrderAttempts = 0
        }

        const missingFields = Array.isArray(voiceResult?.missingFields) ? voiceResult.missingFields : []
        if (missingFields.length > 0) {
          dispatch({
            type: "SET_VOICE_STATUS",
            ready: false,
            message:
              callStatus && callStatus !== "ended"
                ? `Call is ${callStatus}. Waiting for transcript and fields: ${missingFields.join(", ")}`
                : `Waiting for voice capture fields: ${missingFields.join(", ")}`,
          })
        }

        if (callStatus === "ended" && endedWithoutOrderAttempts >= 3) {
          break
        }
      }

      dispatch({
        type: "SET_VOICE_STATUS",
        ready: false,
        message: "Voice call completed, but a submit-ready order was not extracted yet.",
      })
      addTranscript("agent", "Voice call finished, but the extracted result is not yet in the required order format.")
    } catch (err) {
      const message = err instanceof Error ? err.message : "Outbound voice system failed."
      dispatch({ type: "SET_VOICE_STATUS", ready: false, message })
      addTranscript("agent", message)
    }
  }, [addTranscript, clearAutoSubmit, startLiveAudio, startOrderOrchestration, stopLiveAudio])

  const handleSubmitOrder = useCallback(async () => {
    if (!state.voiceOrderReady) {
      return
    }
    await startOrderOrchestration(state.order)
  }, [startOrderOrchestration, state.order, state.voiceOrderReady])

  const handleOrderChange = useCallback((order: Order) => {
    currentOrderRef.current = order
    dispatch({ type: "SET_ORDER", order })
    dispatch({
      type: "SET_VOICE_STATUS",
      ready: true,
      message: "Order edited manually and ready for agent network submission.",
    })
  }, [])

  const handleNewCall = useCallback(() => {
    clearAutoSubmit()
    stopLiveAudio()
    currentOrderRef.current = { ...DEFAULT_ORDER }
    dispatch({ type: "RESET" })
  }, [clearAutoSubmit, stopLiveAudio])

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      <SynkHeader
        phase={state.phase}
        backendSource={state.backendSource}
        backendMessage={state.backendMessage || undefined}
      />

      <ResizablePanelGroup direction="horizontal" className="flex-1">
        <ResizablePanel defaultSize={33} minSize={25} maxSize={45}>
          <VoiceAgentPanel
            phase={state.phase}
            order={state.order}
            voiceOrderReady={state.voiceOrderReady}
            voiceStatusMessage={state.voiceStatusMessage}
            liveAudioStatus={state.liveAudioStatus}
            transcript={state.transcript}
            consensus={state.consensus}
            callHistory={state.callHistory}
            onAcceptCall={handleStartSystem}
            onOrderChange={handleOrderChange}
            onSubmitOrder={handleSubmitOrder}
            onNewCall={handleNewCall}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel defaultSize={67} minSize={45}>
          <OrchestrationPanel
            phase={state.phase}
            activeAgents={state.activeAgents}
            proposals={state.proposals}
            allProposals={state.allProposals}
            rounds={state.rounds}
            consensus={state.consensus}
            order={state.order}
            agentMessages={state.agentMessages}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
