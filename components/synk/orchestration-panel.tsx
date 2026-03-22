"use client"

import { useRef, useEffect, useState, useMemo, useCallback, type PointerEvent as ReactPointerEvent } from "react"
import Image from "next/image"
import type {
  DemoPhase,
  AgentId,
  AgentProposal,
  RoundSummary,
  ConsensusResult,
  Order,
  AgentMessage,
  ActionStep,
} from "@/lib/synk/types"
import { AGENT_CONFIGS } from "@/lib/synk/types"
import { ConsensusCard } from "./consensus-card"
import {
  Zap,
  Loader2,
  Terminal,
  Database,
  Brain,
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  GripVertical,
} from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"

const AGENT_AVATARS: Record<AgentId | "orchestrator", string> = {
  production: "/agents/production.jpg",
  finance: "/agents/finance.jpg",
  logistics: "/agents/logistics.jpg",
  procurement: "/agents/procurement.jpg",
  sales: "/agents/sales.jpg",
  orchestrator: "/agents/orchestrator.jpg",
}

const STEP_ICONS: Record<
  ActionStep["kind"],
  { Icon: React.ComponentType<{ className?: string }>; bg: string; fg: string; label: string }
> = {
  tool_call: { Icon: Terminal, bg: "bg-blue-50", fg: "text-blue-600", label: "TOOL" },
  tool_result: { Icon: Database, bg: "bg-emerald-50", fg: "text-emerald-600", label: "RESULT" },
  thinking: { Icon: Brain, bg: "bg-amber-50", fg: "text-amber-600", label: "THINKING" },
  response: { Icon: ArrowRight, bg: "bg-indigo-50", fg: "text-indigo-600", label: "RESPONSE" },
  objection: { Icon: AlertTriangle, bg: "bg-red-50", fg: "text-red-600", label: "OBJECTION" },
  agreement: { Icon: CheckCircle2, bg: "bg-emerald-50", fg: "text-emerald-600", label: "AGREED" },
}

interface AgentLayoutMeta {
  id: AgentId
  calloutSide: "left" | "right" | "bottom"
}

type LayoutNodeId = AgentId | "orchestrator"
type LayoutPosition = { x: number; y: number }
type DragState =
  | { type: "node"; id: LayoutNodeId }
  | { type: "callout"; id: AgentId; startClientX: number; startClientY: number; startOffsetX: number; startOffsetY: number }
  | { type: "log-panel"; startClientY: number; startHeight: number }

const AGENT_LAYOUTS: AgentLayoutMeta[] = [
  { id: "production", calloutSide: "right" },
  { id: "finance", calloutSide: "left" },
  { id: "sales", calloutSide: "right" },
  { id: "logistics", calloutSide: "left" },
  { id: "procurement", calloutSide: "right" },
]

const DEFAULT_NODE_POSITIONS: Record<LayoutNodeId, LayoutPosition> = {
  orchestrator: { x: 50, y: 48 },
  production: { x: 50, y: 8 },
  finance: { x: 85, y: 35 },
  sales: { x: 15, y: 35 },
  logistics: { x: 75, y: 78 },
  procurement: { x: 25, y: 78 },
}

const DEFAULT_CALLOUT_OFFSETS: Record<AgentId, { x: number; y: number }> = {
  production: { x: 54, y: -34 },
  finance: { x: -234, y: -34 },
  sales: { x: 54, y: -34 },
  logistics: { x: -234, y: -34 },
  procurement: { x: 54, y: -34 },
}

const AGENT_NODE_SIZE = 64
const AGENT_PULSE_SIZE = 82
const ORCHESTRATOR_SIZE = 82

interface OrchestrationPanelProps {
  phase: DemoPhase
  activeAgents: Set<AgentId>
  proposals: Map<AgentId, AgentProposal>
  allProposals: AgentProposal[]
  rounds: RoundSummary[]
  consensus: ConsensusResult | null
  order: Order
  agentMessages: AgentMessage[]
}

function AgentCallout({
  proposal,
  color,
  isLive,
  onDragStart,
}: {
  proposal: AgentProposal | undefined
  color: string
  isLive: boolean
  onDragStart?: (event: ReactPointerEvent<HTMLDivElement>) => void
}) {
  const [visibleStep, setVisibleStep] = useState(-1)
  const [expanded, setExpanded] = useState(false)
  const [expandedActionKeys, setExpandedActionKeys] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!isLive || !proposal?.actions?.length) {
      setVisibleStep(-1)
      return
    }
    setVisibleStep(0)
    let idx = 0
    const iv = setInterval(() => {
      idx += 1
      if (idx >= proposal.actions.length) {
        clearInterval(iv)
        return
      }
      setVisibleStep(idx)
    }, 700)
    return () => clearInterval(iv)
  }, [isLive, proposal?.actions, proposal?.round])

  if (!proposal?.actions?.length) return null

  const toggleAction = (key: string) => {
    setExpandedActionKeys((prev) => ({
      ...prev,
      [key]: !prev[key],
    }))
  }

  const statusBg = proposal.status === "agreed" ? "#dcfce7" : proposal.status === "objecting" ? "#fef2f2" : `${color}15`
  const statusFg = proposal.status === "agreed" ? "#16a34a" : proposal.status === "objecting" ? "#dc2626" : color

  if (!isLive) {
    return (
      <div className="relative w-[190px] rounded-xl bg-card border border-border shadow-lg shadow-black/5 overflow-hidden animate-pop-in">
        <div className="h-[2px]" style={{ background: color }} />
        <div
          className="absolute top-1.5 right-1.5 z-10 flex h-6 w-6 cursor-grab items-center justify-center rounded-md bg-secondary/80 text-muted-foreground transition-colors hover:bg-secondary"
          onPointerDown={onDragStart}
          title="Drag proposal box"
        >
          <GripVertical className="h-3.5 w-3.5" />
        </div>
        <button
          className="w-full flex items-center gap-1.5 px-2.5 py-2 pr-10 hover:bg-secondary/50 transition-colors cursor-pointer"
          onClick={() => setExpanded((value) => !value)}
        >
          <div className="flex items-center gap-0.5 flex-1 min-w-0">
            {proposal.actions.map((action, i) => {
              const meta = STEP_ICONS[action.kind]
              return (
                <div
                  key={i}
                  className={`w-5 h-5 rounded-md flex items-center justify-center shrink-0 ${meta.bg}`}
                  title={`${meta.label}: ${action.label}`}
                >
                  <meta.Icon className={`w-2.5 h-2.5 ${meta.fg}`} />
                </div>
              )
            })}
          </div>
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded-full shrink-0" style={{ backgroundColor: statusBg, color: statusFg }}>
            {proposal.status === "agreed" ? "OK" : proposal.status === "objecting" ? "OBJ" : "..."}
          </span>
        </button>
        {expanded && (
          <div className="max-h-[150px] overflow-y-auto px-2 pb-2 space-y-1 border-t border-border">
            {proposal.actions.map((action, i) => {
              const meta = STEP_ICONS[action.kind]
              const actionKey = `${proposal.round}-${action.kind}-${i}`
              const isExpanded = Boolean(expandedActionKeys[actionKey])
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => toggleAction(actionKey)}
                  className={`w-full text-left rounded-lg p-1.5 ${meta.bg}`}
                >
                  <div className="flex items-center gap-1 mb-0.5">
                    <meta.Icon className={`w-2.5 h-2.5 shrink-0 ${meta.fg}`} />
                    <span className={`text-[8px] font-bold ${meta.fg}`}>{meta.label}</span>
                    <code className="text-[7px] font-mono text-muted-foreground truncate">{action.label}</code>
                  </div>
                  <p className={`text-[8px] leading-snug text-secondary-foreground ${isExpanded ? "whitespace-normal break-words" : "line-clamp-2"}`}>{action.detail}</p>
                  {action.data && Object.keys(action.data).length > 0 && (
                    <div className="flex flex-wrap gap-0.5 mt-0.5">
                      {Object.entries(action.data)
                        .slice(0, 3)
                        .map(([k, v]) => (
                          <span key={k} className={`text-[7px] font-mono px-1 py-0.5 rounded ${meta.bg} ${meta.fg}`}>
                            {k}: <strong>{String(v)}</strong>
                          </span>
                        ))}
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  if (visibleStep < 0) return null
  const shownActions = proposal.actions.slice(Math.max(0, visibleStep - 1), visibleStep + 1)

  return (
    <div className="relative w-[190px] rounded-xl bg-card border border-border shadow-lg shadow-black/5 overflow-hidden animate-pop-in">
      <div className="h-[2px]" style={{ background: color }} />
      <div className="flex items-center justify-between px-2.5 py-1.5">
        <span className="text-[9px] font-mono font-bold text-muted-foreground">R{proposal.round}</span>
        <div className="flex items-center gap-1.5">
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded-full" style={{ backgroundColor: statusBg, color: statusFg }}>
            {proposal.status.toUpperCase()}
          </span>
          <div
            className="flex h-6 w-6 cursor-grab items-center justify-center rounded-md bg-secondary/80 text-muted-foreground transition-colors hover:bg-secondary"
            onPointerDown={onDragStart}
            title="Drag proposal box"
          >
            <GripVertical className="h-3.5 w-3.5" />
          </div>
        </div>
      </div>
      <div className="max-h-[120px] overflow-y-auto px-2 pb-2 space-y-1">
        {shownActions.map((action, i) => {
          const meta = STEP_ICONS[action.kind]
          const isLatest = i === shownActions.length - 1
          const actionKey = `${proposal.round}-${action.kind}-${i}`
          const isExpanded = Boolean(expandedActionKeys[actionKey])
          return (
            <button
              key={`${proposal.round}-${action.kind}-${i}`}
              type="button"
              onClick={() => toggleAction(actionKey)}
              className={`w-full text-left rounded-lg p-1.5 ${isLatest ? meta.bg : "bg-secondary/50"}`}
              style={{ opacity: isLatest ? 1 : 0.6 }}
            >
              <div className="flex items-center gap-1 mb-0.5">
                <meta.Icon className={`w-2.5 h-2.5 shrink-0 ${meta.fg}`} />
                <span className={`text-[8px] font-bold ${meta.fg}`}>{meta.label}</span>
                {(action.kind === "tool_call" || action.kind === "tool_result") && (
                  <code className="text-[7px] font-mono text-muted-foreground truncate">{action.label}</code>
                )}
              </div>
              <p className={`text-[8px] leading-snug text-secondary-foreground ${isExpanded ? "whitespace-normal break-words" : "line-clamp-2"}`}>{action.detail}</p>
              {action.data && Object.keys(action.data).length > 0 && (
                <div className="flex flex-wrap gap-0.5 mt-0.5">
                  {Object.entries(action.data)
                    .slice(0, 3)
                    .map(([k, v]) => (
                      <span key={k} className={`text-[7px] font-mono px-1 py-0.5 rounded ${meta.bg} ${meta.fg}`}>
                        {k}: <strong>{String(v)}</strong>
                      </span>
                    ))}
                </div>
              )}
            </button>
          )
        })}
        {visibleStep < proposal.actions.length - 1 && (
          <div className="flex items-center gap-1 px-1.5">
            <Loader2 className="w-2.5 h-2.5 animate-spin text-muted-foreground" />
            <span className="text-[8px] text-muted-foreground animate-pulse">Processing...</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function OrchestrationPanel({
  phase,
  activeAgents,
  proposals,
  allProposals,
  rounds,
  consensus,
  order,
  agentMessages,
}: OrchestrationPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const dragStateRef = useRef<DragState | null>(null)
  const [dims, setDims] = useState({ w: 800, h: 500 })
  const [selectedRound, setSelectedRound] = useState<number>(1)
  const [nodePositions, setNodePositions] = useState<Record<LayoutNodeId, LayoutPosition>>(DEFAULT_NODE_POSITIONS)
  const [calloutOffsets, setCalloutOffsets] = useState<Record<AgentId, { x: number; y: number }>>(DEFAULT_CALLOUT_OFFSETS)
  const [draggingNodeId, setDraggingNodeId] = useState<LayoutNodeId | null>(null)
  const [draggingCalloutId, setDraggingCalloutId] = useState<AgentId | null>(null)
  const [logPanelHeight, setLogPanelHeight] = useState(108)

  const isIdle = phase === "idle" || phase === "incoming-call" || phase === "active-call"
  const isNegotiating = phase.startsWith("round-") || phase === "order-broadcast"
  const isDone = phase === "consensus" || phase === "callback" || phase === "done"
  const currentRound = phase === "round-1" ? 1 : phase === "round-2" ? 2 : phase === "round-3" ? 3 : isDone ? 3 : 0

  useEffect(() => {
    if (consensus) {
      setSelectedRound(0)
    } else if (currentRound > 0) {
      setSelectedRound(currentRound)
    }
  }, [currentRound, consensus])

  const roundProposals = useMemo(() => {
    const map: Partial<Record<AgentId, AgentProposal>> = {}
    for (const proposal of allProposals) {
      if (proposal.round === selectedRound) {
        map[proposal.agentId] = proposal
      }
    }
    return map
  }, [allProposals, selectedRound])

  const roundMessages = useMemo(() => {
    return agentMessages.filter((message) => message.round === selectedRound)
  }, [agentMessages, selectedRound])

  const maxRound = Math.max(currentRound, rounds.length)

  const [activeLink, setActiveLink] = useState<AgentId | null>(null)
  useEffect(() => {
    const lastMsg = agentMessages[agentMessages.length - 1]
    if (!lastMsg) return
    const id = lastMsg.from === "orchestrator" ? (lastMsg.to as AgentId) : (lastMsg.from as AgentId)
    setActiveLink(id)
    const t = setTimeout(() => setActiveLink(null), 800)
    return () => clearTimeout(t)
  }, [agentMessages])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        setDims({ w: entry.contentRect.width, h: entry.contentRect.height })
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const updateNodePosition = useCallback((id: LayoutNodeId, clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0 || rect.height <= 0) return

    const nextX = Math.min(92, Math.max(8, ((clientX - rect.left) / rect.width) * 100))
    const nextY = Math.min(88, Math.max(8, ((clientY - rect.top) / rect.height) * 100))

    setNodePositions((prev) => ({
      ...prev,
      [id]: { x: nextX, y: nextY },
    }))
  }, [])

  const stopDragging = useCallback(() => {
    if (!dragStateRef.current) return
    dragStateRef.current = null
    setDraggingNodeId(null)
    setDraggingCalloutId(null)
    document.body.style.cursor = ""
    document.body.style.userSelect = ""
  }, [])

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      if (!dragStateRef.current) return
      if (dragStateRef.current.type === "node") {
        updateNodePosition(dragStateRef.current.id, event.clientX, event.clientY)
        return
      }

      if (dragStateRef.current.type === "log-panel") {
        const dragState = dragStateRef.current
        const deltaY = dragState.startClientY - event.clientY
        setLogPanelHeight(Math.min(240, Math.max(72, dragState.startHeight + deltaY)))
        return
      }

      const dragState = dragStateRef.current
      const deltaX = event.clientX - dragState.startClientX
      const deltaY = event.clientY - dragState.startClientY
      setCalloutOffsets((prev) => ({
        ...prev,
        [dragState.id]: {
          x: dragState.startOffsetX + deltaX,
          y: dragState.startOffsetY + deltaY,
        },
      }))
    }

    const handlePointerUp = () => {
      stopDragging()
    }

    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)

    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
    }
  }, [stopDragging, updateNodePosition])

  const startDragging = useCallback((id: LayoutNodeId, event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    dragStateRef.current = { type: "node", id }
    setDraggingNodeId(id)
    setDraggingCalloutId(null)
    document.body.style.cursor = "grabbing"
    document.body.style.userSelect = "none"
    updateNodePosition(id, event.clientX, event.clientY)
  }, [updateNodePosition])

  const startCalloutDragging = useCallback((id: AgentId, event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const currentOffset = calloutOffsets[id]
    dragStateRef.current = {
      type: "callout",
      id,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startOffsetX: currentOffset.x,
      startOffsetY: currentOffset.y,
    }
    setDraggingCalloutId(id)
    setDraggingNodeId(null)
    document.body.style.cursor = "grabbing"
    document.body.style.userSelect = "none"
  }, [calloutOffsets])

  const startLogPanelDragging = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    dragStateRef.current = {
      type: "log-panel",
      startClientY: event.clientY,
      startHeight: logPanelHeight,
    }
    setDraggingNodeId(null)
    setDraggingCalloutId(null)
    document.body.style.cursor = "ns-resize"
    document.body.style.userSelect = "none"
  }, [logPanelHeight])

  const px = (layout: LayoutPosition) => ({
    x: (layout.x / 100) * dims.w,
    y: (layout.y / 100) * dims.h,
  })

  const orchPx = px(nodePositions.orchestrator)

  return (
    <div className="flex flex-col h-full bg-background overflow-hidden">
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">Agent Orchestration</span>
        </div>
        {!isIdle && (
          <div className="flex items-center gap-3">
            {isNegotiating && (
              <span className="flex items-center gap-1.5 text-[10px] font-semibold text-primary">
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                LIVE
              </span>
            )}
            <span className="text-[10px] font-mono text-muted-foreground">
              {currentRound > 0 ? `Round ${Math.min(currentRound, 3)}/3` : "Initializing"}
            </span>
          </div>
        )}
      </div>

      {maxRound > 0 && (
        <div className="shrink-0 border-b border-border bg-card px-4 py-1.5 flex items-center gap-1">
          {[1, 2, 3].map((round) => {
            const isAvailable = round <= maxRound
            const isSelected = round === selectedRound
            const isLiveRound = round === currentRound && isNegotiating
            return (
              <button
                key={round}
                onClick={() => isAvailable && setSelectedRound(round)}
                disabled={!isAvailable}
                className={`
                  flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all
                  ${isSelected
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : isAvailable
                      ? "bg-secondary text-secondary-foreground hover:bg-accent"
                      : "text-muted-foreground/40 cursor-not-allowed"
                  }
                `}
              >
                {isLiveRound && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
                Round {round}
                {rounds[round - 1] && !isLiveRound && <CheckCircle2 className="w-3 h-3 opacity-60" />}
              </button>
            )
          })}
          {consensus && (
            <button
              onClick={() => setSelectedRound(0)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ml-auto ${selectedRound === 0 ? "bg-emerald-600 text-white shadow-sm" : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"}`}
            >
              <CheckCircle2 className="w-3 h-3" />
              Consensus
            </button>
          )}
        </div>
      )}

      <div ref={containerRef} className="flex-1 relative min-h-0 overflow-hidden">
        {consensus && selectedRound === 0 && (
          <div className="absolute inset-0 z-30 bg-background/90 backdrop-blur-sm overflow-y-auto p-6">
            <ConsensusCard consensus={consensus} order={order} finalProposals={rounds[rounds.length - 1]?.proposals || []} />
          </div>
        )}

        <svg className="absolute inset-0 w-full h-full" style={{ zIndex: 1 }}>
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#94a3b8" strokeWidth="0.3" opacity="0.1" />
            </pattern>
          </defs>

          <rect width="100%" height="100%" fill="url(#grid)" />

          {AGENT_LAYOUTS.map((layout) => {
            const config = AGENT_CONFIGS.find((candidate) => candidate.id === layout.id)!
            const agentPx = px(nodePositions[layout.id])
            const isActive = activeAgents.has(layout.id)
            const isHighlighted = activeLink === layout.id
            return (
              <g key={layout.id}>
                <line
                  x1={orchPx.x}
                  y1={orchPx.y}
                  x2={agentPx.x}
                  y2={agentPx.y}
                  stroke={config.color}
                  strokeWidth={isHighlighted ? 2.5 : 1}
                  opacity={isHighlighted ? 0.4 : isActive ? 0.12 : 0.05}
                  strokeLinecap="round"
                />
                {isActive && isNegotiating && (
                  <line
                    x1={orchPx.x}
                    y1={orchPx.y}
                    x2={agentPx.x}
                    y2={agentPx.y}
                    stroke={config.color}
                    strokeWidth={1.5}
                    strokeDasharray="4 8"
                    className="animate-dash-flow"
                    opacity={isHighlighted ? 0.5 : 0.12}
                    strokeLinecap="round"
                  />
                )}
                {isHighlighted && (
                  <circle r="4" fill={config.color} opacity="0.8">
                    <animateMotion dur="0.5s" fill="freeze" path={`M${orchPx.x},${orchPx.y} L${agentPx.x},${agentPx.y}`} />
                    <animate attributeName="opacity" from="0.8" to="0" dur="0.5s" fill="freeze" />
                  </circle>
                )}
              </g>
            )
          })}
        </svg>

        <div className="absolute inset-0" style={{ zIndex: 2, pointerEvents: "none" }}>
          <div
            className="absolute flex flex-col items-center cursor-grab"
            style={{
              left: `${nodePositions.orchestrator.x}%`,
              top: `${nodePositions.orchestrator.y}%`,
              transform: "translate(-50%, -50%)",
              pointerEvents: "auto",
            }}
            onPointerDown={(event) => startDragging("orchestrator", event)}
          >
            <div
              className={`rounded-full bg-card border-2 shadow-lg overflow-hidden ${isNegotiating ? "border-primary shadow-primary/20" : "border-border"} ${draggingNodeId === "orchestrator" ? "scale-105" : ""}`}
              style={{ width: ORCHESTRATOR_SIZE, height: ORCHESTRATOR_SIZE }}
            >
              <Image src={AGENT_AVATARS.orchestrator} alt="Orchestrator" width={ORCHESTRATOR_SIZE} height={ORCHESTRATOR_SIZE} className="object-cover w-full h-full" />
            </div>
            <span className="text-[11px] font-semibold text-muted-foreground mt-2 tracking-wide">ORCHESTRATOR</span>
          </div>

          {AGENT_LAYOUTS.map((layout) => {
            const config = AGENT_CONFIGS.find((candidate) => candidate.id === layout.id)!
            const isActive = activeAgents.has(layout.id)
            const proposal = roundProposals[layout.id]
            const position = nodePositions[layout.id]
            const calloutOffset = calloutOffsets[layout.id]

            return (
              <div key={layout.id}>
                <div
                  className="absolute flex flex-col items-center cursor-grab"
                  style={{
                    left: `${position.x}%`,
                    top: `${position.y}%`,
                    transform: "translate(-50%, -50%)",
                    pointerEvents: "auto",
                  }}
                  onPointerDown={(event) => startDragging(layout.id, event)}
                >
                  {isActive && isNegotiating && (
                    <div
                      className="absolute rounded-full animate-ring-pulse"
                      style={{ width: AGENT_PULSE_SIZE, height: AGENT_PULSE_SIZE, border: `2px solid ${config.color}30` }}
                    />
                  )}
                  <div
                    className={`rounded-full bg-card border-2 shadow-md overflow-hidden transition-all ${draggingNodeId === layout.id ? "scale-105" : ""}`}
                    style={{
                      width: AGENT_NODE_SIZE,
                      height: AGENT_NODE_SIZE,
                      borderColor: isActive ? config.color : "#e2e8f0",
                      boxShadow: isActive ? `0 4px 14px ${config.color}25` : undefined,
                    }}
                  >
                    <Image src={AGENT_AVATARS[layout.id]} alt={config.name} width={AGENT_NODE_SIZE} height={AGENT_NODE_SIZE} className="object-cover w-full h-full" />
                  </div>
                  <span className="text-[11px] font-bold mt-1.5" style={{ color: isActive ? config.color : "#94a3b8" }}>
                    {config.name}
                  </span>
                  <span className="text-[8px] text-muted-foreground">{config.role}</span>

                  {proposal && (
                    <div
                      className="absolute top-0 right-0 w-3.5 h-3.5 rounded-full border-2 border-card"
                      style={{ backgroundColor: proposal.status === "agreed" ? "#16a34a" : proposal.status === "objecting" ? "#dc2626" : config.color }}
                    />
                  )}
                </div>

                {proposal && (
                  <div
                    className="absolute"
                    style={{
                      left: `${position.x}%`,
                      top: `${position.y}%`,
                      transform: `translate(${calloutOffset.x}px, ${calloutOffset.y}px)`,
                      pointerEvents: "auto",
                    }}
                  >
                    <div className={draggingCalloutId === layout.id ? "scale-[1.02]" : ""}>
                      <AgentCallout
                        proposal={proposal}
                        color={config.color}
                        isLive={selectedRound === currentRound && isNegotiating}
                        onDragStart={(event) => startCalloutDragging(layout.id, event)}
                      />
                    </div>
                  </div>
                )}

                {!proposal && isActive && isNegotiating && (
                  <div
                    className="absolute flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-card border border-border shadow-sm"
                    style={{
                      left: `${position.x}%`,
                      top: `${position.y}%`,
                      transform: `translate(${layout.calloutSide === "right" ? 50 : -112}px, -10px)`,
                      pointerEvents: "auto",
                    }}
                  >
                    <Loader2 className="w-3 h-3 animate-spin" style={{ color: config.color }} />
                    <span className="text-[9px] font-medium text-muted-foreground">Analyzing...</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {isIdle && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/60 backdrop-blur-sm">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center mx-auto mb-4">
                <Image src={AGENT_AVATARS.orchestrator} alt="Orchestrator" width={48} height={48} className="rounded-full" />
              </div>
              <p className="text-sm font-medium text-muted-foreground">Waiting for order submission</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Submit an order to activate agents</p>
            </div>
          </div>
        )}
      </div>

      {roundMessages.length > 0 && selectedRound > 0 && (
        <div className="shrink-0 border-t border-border bg-card" style={{ height: logPanelHeight }}>
          <div
            className="flex h-4 cursor-row-resize items-center justify-center border-b border-border/70 bg-secondary/30"
            onPointerDown={startLogPanelDragging}
            title="Drag to resize logs"
          >
            <div className="h-1 w-16 rounded-full bg-muted-foreground/30" />
          </div>
          <ScrollArea className="h-[calc(100%-16px)]">
            <div className="space-y-1 px-4 py-2">
              {roundMessages.map((msg) => {
                const fromConfig = AGENT_CONFIGS.find((agent) => agent.id === msg.from)
                const color = fromConfig?.color || "#6366f1"
                return (
                  <div key={msg.id} className="flex items-start gap-2 text-[10px]">
                    <div className="mt-0.5 h-4 w-4 shrink-0 overflow-hidden rounded-full">
                      <Image
                        src={AGENT_AVATARS[msg.from as AgentId] || AGENT_AVATARS.orchestrator}
                        alt={String(msg.from)}
                        width={16}
                        height={16}
                        className="h-full w-full object-cover"
                      />
                    </div>
                    <div className="min-w-0">
                      <span className="font-bold" style={{ color }}>
                        {fromConfig?.name || "Orchestrator"}
                      </span>
                      <span
                        className="ml-1.5 rounded-full px-1.5 py-0.5 text-[8px] font-bold"
                        style={{ backgroundColor: `${color}10`, color }}
                      >
                        {msg.type.toUpperCase()}
                      </span>
                      <p className="text-muted-foreground">{msg.message}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  )
}
