"use client"

import { useEffect, useState } from "react"
import { AGENT_CONFIGS, type AgentId, type AgentProposal, type AgentMessage } from "@/lib/synk/types"
import { Factory, DollarSign, Truck, Package, Users, Cpu } from "lucide-react"

const ICONS: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  Factory, DollarSign, Truck, Package, Users,
}

interface AgentNetworkProps {
  activeAgents: Set<AgentId>
  proposals: Map<AgentId, AgentProposal>
  isNegotiating: boolean
  latestMessage?: AgentMessage | null
}

// Hexagon path helper
function hexPath(cx: number, cy: number, r: number): string {
  const pts = Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i - Math.PI / 2
    return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`
  })
  return `M${pts.join("L")}Z`
}

export function AgentNetwork({ activeAgents, proposals, isNegotiating, latestMessage }: AgentNetworkProps) {
  const [activeLine, setActiveLine] = useState<{ from: string; to: string } | null>(null)
  const [particles, setParticles] = useState<{ id: number; from: string; to: string; progress: number }[]>([])

  const cx = 250
  const cy = 210
  const radius = 150

  const agentPositions = AGENT_CONFIGS.map((agent, i) => {
    const angle = (i * 2 * Math.PI) / 5 - Math.PI / 2
    return {
      ...agent,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    }
  })

  const getPos = (id: string) => {
    if (id === "orchestrator" || id === "all") return { x: cx, y: cy }
    const found = agentPositions.find(a => a.id === id)
    return found ? { x: found.x, y: found.y } : { x: cx, y: cy }
  }

  // Highlight active communication line when new messages arrive
  useEffect(() => {
    if (!latestMessage) return
    const from = latestMessage.from
    const to = latestMessage.to
    setActiveLine({ from, to })

    // Add particle
    const pId = Date.now()
    setParticles(prev => [...prev, { id: pId, from, to, progress: 0 }])

    const timer = setTimeout(() => {
      setActiveLine(null)
      setParticles(prev => prev.filter(p => p.id !== pId))
    }, 1200)
    return () => clearTimeout(timer)
  }, [latestMessage])

  return (
    <div className="relative w-full">
      <svg viewBox="0 0 500 420" className="w-full h-auto" role="img" aria-label="Agent network visualization">
        <defs>
          {AGENT_CONFIGS.map((agent) => (
            <radialGradient key={`grad-${agent.id}`} id={`grad-${agent.id}`}>
              <stop offset="0%" stopColor={agent.color} stopOpacity="0.2" />
              <stop offset="100%" stopColor={agent.color} stopOpacity="0.02" />
            </radialGradient>
          ))}
          <radialGradient id="grad-moderator">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.02" />
          </radialGradient>
          {/* Glow filters */}
          {AGENT_CONFIGS.map((agent) => (
            <filter key={`glow-${agent.id}`} id={`glow-${agent.id}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feFlood floodColor={agent.color} floodOpacity="0.4" />
              <feComposite in2="blur" operator="in" />
              <feMerge>
                <feMergeNode />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}
          <filter id="glow-mod" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feFlood floodColor="#06b6d4" floodOpacity="0.5" />
            <feComposite in2="blur" operator="in" />
            <feMerge>
              <feMergeNode />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background grid pattern */}
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="currentColor" strokeWidth="0.3" className="text-border" opacity="0.3" />
        </pattern>
        <rect width="500" height="420" fill="url(#grid)" opacity="0.5" />

        {/* Connection lines from orchestrator to agents */}
        {agentPositions.map((agent) => {
          const isActive = activeAgents.has(agent.id)
          const isHighlighted = activeLine && (activeLine.from === agent.id || activeLine.to === agent.id)
          return (
            <g key={`line-${agent.id}`}>
              <line
                x1={cx} y1={cy} x2={agent.x} y2={agent.y}
                stroke={agent.color}
                strokeWidth={isHighlighted ? 2.5 : isActive ? 1.5 : 0.5}
                opacity={isHighlighted ? 0.8 : isActive ? 0.2 : 0.06}
                strokeLinecap="round"
              />
              {isActive && isNegotiating && (
                <line
                  x1={cx} y1={cy} x2={agent.x} y2={agent.y}
                  stroke={agent.color}
                  strokeWidth={1.5}
                  strokeDasharray="6 8"
                  className="animate-dash-flow"
                  opacity={isHighlighted ? 0.9 : 0.35}
                />
              )}
            </g>
          )
        })}

        {/* Inter-agent connection lines (only when both active) */}
        {agentPositions.map((a, i) =>
          agentPositions.slice(i + 1).map((b) => {
            const bothActive = activeAgents.has(a.id) && activeAgents.has(b.id)
            if (!bothActive) return null
            const isHighlighted = activeLine &&
              ((activeLine.from === a.id && activeLine.to === b.id) ||
               (activeLine.from === b.id && activeLine.to === a.id))
            return (
              <line
                key={`inter-${a.id}-${b.id}`}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={isHighlighted ? "#fff" : "var(--border)"}
                strokeWidth={isHighlighted ? 1.5 : 0.4}
                opacity={isHighlighted ? 0.6 : 0.15}
                strokeDasharray={isHighlighted ? "4 4" : "2 6"}
                className={isHighlighted ? "animate-dash-flow" : ""}
              />
            )
          })
        )}

        {/* Data flow particle effects */}
        {particles.map((p) => {
          const fromPos = getPos(p.from)
          const toPos = getPos(p.to)
          const fromAgent = AGENT_CONFIGS.find(a => a.id === p.from)
          const color = fromAgent?.color || "#06b6d4"
          return (
            <circle key={p.id} r="4" fill={color} opacity="0.9" filter={`url(#glow-${p.from})`}>
              <animateMotion dur="0.8s" fill="freeze" path={`M${fromPos.x},${fromPos.y} L${toPos.x},${toPos.y}`} />
              <animate attributeName="r" from="4" to="0" dur="0.8s" fill="freeze" />
              <animate attributeName="opacity" from="1" to="0" dur="0.8s" fill="freeze" />
            </circle>
          )
        })}

        {/* Orchestrator center node */}
        <g>
          {/* Ambient glow ring */}
          <circle cx={cx} cy={cy} r={44} fill="url(#grad-moderator)" />
          {isNegotiating && (
            <>
              <circle cx={cx} cy={cy} r={40} fill="none" stroke="#06b6d4" strokeWidth={1} opacity={0.15} className="animate-ring-pulse" />
              <circle cx={cx} cy={cy} r={48} fill="none" stroke="#06b6d4" strokeWidth={0.5} opacity={0.08} className="animate-ring-pulse" style={{ animationDelay: "0.5s" }} />
            </>
          )}
          <path
            d={hexPath(cx, cy, 32)}
            fill="var(--card)"
            stroke="#06b6d4"
            strokeWidth={isNegotiating ? 2 : 1}
            filter={isNegotiating ? "url(#glow-mod)" : undefined}
          />
          <foreignObject x={cx - 12} y={cy - 12} width={24} height={24}>
            <Cpu className="w-6 h-6" style={{ color: "#06b6d4" }} />
          </foreignObject>
          <text x={cx} y={cy + 50} textAnchor="middle" className="text-[9px] font-mono uppercase tracking-widest" fill="#06b6d4" fontWeight="600">
            Orchestrator
          </text>
        </g>

        {/* Agent nodes */}
        {agentPositions.map((agent) => {
          const isActive = activeAgents.has(agent.id)
          const proposal = proposals.get(agent.id)
          const IconComp = ICONS[agent.icon]
          const isAgreed = proposal?.status === "agreed"
          const isObjecting = proposal?.status === "objecting"

          return (
            <g key={agent.id}>
              {/* Ambient glow */}
              {isActive && (
                <circle cx={agent.x} cy={agent.y} r={38} fill={`url(#grad-${agent.id})`} />
              )}

              {/* Pulsing ring for active nodes */}
              {isActive && !isAgreed && (
                <path
                  d={hexPath(agent.x, agent.y, 30)}
                  fill="none"
                  stroke={agent.color}
                  strokeWidth={0.8}
                  opacity={0.25}
                  className="animate-pulse-line"
                />
              )}

              {/* Agreed ring */}
              {isAgreed && (
                <path
                  d={hexPath(agent.x, agent.y, 30)}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  opacity={0.6}
                />
              )}

              {/* Main hexagon node */}
              <path
                d={hexPath(agent.x, agent.y, 26)}
                fill="var(--card)"
                stroke={isAgreed ? "#10b981" : isObjecting ? "#ef4444" : agent.color}
                strokeWidth={isActive ? 2 : 0.8}
                opacity={isActive ? 1 : 0.3}
                filter={isActive ? `url(#glow-${agent.id})` : undefined}
              />

              {/* Status indicator dot */}
              {proposal && (
                <circle
                  cx={agent.x + 20} cy={agent.y - 20} r={5}
                  fill={isAgreed ? "#10b981" : isObjecting ? "#ef4444" : agent.color}
                  stroke="var(--card)" strokeWidth={2}
                />
              )}

              {/* Icon */}
              <foreignObject x={agent.x - 11} y={agent.y - 11} width={22} height={22}>
                {IconComp && (
                  <IconComp
                    className="w-[22px] h-[22px]"
                    style={{ color: isActive ? (isAgreed ? "#10b981" : agent.color) : "var(--muted-foreground)" }}
                  />
                )}
              </foreignObject>

              {/* Agent name */}
              <text
                x={agent.x} y={agent.y + 42}
                textAnchor="middle"
                className="text-[10px] font-mono font-semibold uppercase tracking-wider"
                fill={isActive ? agent.color : "var(--muted-foreground)"}
                opacity={isActive ? 1 : 0.4}
              >
                {agent.name}
              </text>

              {/* Status label */}
              {proposal && (
                <text
                  x={agent.x} y={agent.y + 54}
                  textAnchor="middle"
                  className="text-[8px] font-mono"
                  fill={isAgreed ? "#10b981" : isObjecting ? "#ef4444" : agent.color}
                  opacity={0.8}
                >
                  {proposal.status.toUpperCase()}
                </text>
              )}

              {/* Role label */}
              <text
                x={agent.x} y={agent.y + 64}
                textAnchor="middle"
                className="text-[7px] font-mono"
                fill="var(--muted-foreground)"
                opacity={isActive ? 0.5 : 0.2}
              >
                {agent.role}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
