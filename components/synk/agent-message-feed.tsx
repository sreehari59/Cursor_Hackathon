"use client"

import { useEffect, useRef } from "react"
import { AGENT_CONFIGS, type AgentMessage, type AgentId } from "@/lib/synk/types"
import { ArrowRight, AlertTriangle, CheckCircle2, MessageSquare, Zap, CornerDownRight } from "lucide-react"

const TYPE_STYLES: Record<AgentMessage["type"], { icon: React.ComponentType<{ className?: string }>; label: string; cls: string }> = {
  directive: { icon: Zap, label: "DIRECTIVE", cls: "bg-sky-50 text-sky-700 border-sky-200" },
  proposal: { icon: MessageSquare, label: "PROPOSAL", cls: "bg-indigo-50 text-indigo-700 border-indigo-200" },
  objection: { icon: AlertTriangle, label: "OBJECTION", cls: "bg-red-50 text-red-700 border-red-200" },
  counter: { icon: CornerDownRight, label: "COUNTER", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  agreement: { icon: CheckCircle2, label: "AGREED", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  info: { icon: MessageSquare, label: "INFO", cls: "bg-violet-50 text-violet-700 border-violet-200" },
}

function getAgentColor(id: AgentId | "orchestrator" | "all"): string {
  if (id === "orchestrator" || id === "all") return "#6366f1"
  return AGENT_CONFIGS.find(a => a.id === id)?.color || "#888"
}

function getAgentName(id: AgentId | "orchestrator" | "all"): string {
  if (id === "orchestrator") return "Orchestrator"
  if (id === "all") return "All Agents"
  return AGENT_CONFIGS.find(a => a.id === id)?.name || id
}

interface AgentMessageFeedProps {
  messages: AgentMessage[]
}

export function AgentMessageFeed({ messages }: AgentMessageFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  if (messages.length === 0) return null

  let lastRound = 0

  return (
    <div ref={scrollRef} className="flex flex-col gap-1 overflow-y-auto max-h-full pr-1">
      {messages.map((msg, idx) => {
        const style = TYPE_STYLES[msg.type]
        const IconComp = style.icon
        const fromColor = getAgentColor(msg.from)
        const toColor = getAgentColor(msg.to)
        const showRoundDivider = msg.round !== lastRound
        if (showRoundDivider) lastRound = msg.round

        return (
          <div key={msg.id}>
            {showRoundDivider && (
              <div className="flex items-center gap-2 py-2 mt-1">
                <div className="flex-1 h-px bg-border" />
                <span className="text-[9px] font-mono text-primary font-semibold tracking-widest uppercase px-2">
                  Round {msg.round}
                </span>
                <div className="flex-1 h-px bg-border" />
              </div>
            )}

            <div
              className="flex gap-2.5 px-2 py-2 rounded-lg hover:bg-secondary/60 transition-colors animate-float-in"
              style={{ animationDelay: `${idx * 0.03}s` }}
            >
              <div
                className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5"
                style={{ backgroundColor: `${fromColor}12`, border: `1px solid ${fromColor}25` }}
              >
                <span className="text-[9px] font-mono font-bold" style={{ color: fromColor }}>
                  {getAgentName(msg.from).slice(0, 2).toUpperCase()}
                </span>
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                  <span className="text-[10px] font-semibold" style={{ color: fromColor }}>
                    {getAgentName(msg.from)}
                  </span>
                  <ArrowRight className="w-2.5 h-2.5 text-muted-foreground/40" />
                  <span className="text-[10px] font-medium" style={{ color: toColor }}>
                    {getAgentName(msg.to)}
                  </span>
                  <span className={`inline-flex items-center gap-0.5 px-1.5 py-0 rounded text-[8px] font-mono font-semibold border ${style.cls}`}>
                    <IconComp className="w-2.5 h-2.5" />
                    {style.label}
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-foreground/80">{msg.message}</p>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
