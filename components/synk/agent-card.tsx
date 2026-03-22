"use client"

import { useEffect, useState, useRef } from "react"
import type { AgentProposal, ActionStep } from "@/lib/synk/types"
import { AGENT_CONFIGS } from "@/lib/synk/types"
import { Badge } from "@/components/ui/badge"
import {
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Terminal,
  Brain,
  ArrowRight,
  Database,
  ChevronDown,
  ChevronUp,
} from "lucide-react"

const STEP_ICONS: Record<ActionStep["kind"], React.ComponentType<{ className?: string }>> = {
  tool_call: Terminal,
  tool_result: Database,
  thinking: Brain,
  response: ArrowRight,
  objection: AlertTriangle,
  agreement: CheckCircle2,
}

const STEP_STYLES: Record<ActionStep["kind"], { label: string; textCls: string; borderCls: string; bgCls: string }> = {
  tool_call: { label: "TOOL", textCls: "text-sky-700", borderCls: "border-sky-200", bgCls: "bg-sky-50" },
  tool_result: { label: "RESULT", textCls: "text-emerald-700", borderCls: "border-emerald-200", bgCls: "bg-emerald-50" },
  thinking: { label: "THINKING", textCls: "text-amber-700", borderCls: "border-amber-200", bgCls: "bg-amber-50" },
  response: { label: "RESPONSE", textCls: "text-indigo-700", borderCls: "border-indigo-200", bgCls: "bg-indigo-50" },
  objection: { label: "OBJECTION", textCls: "text-red-700", borderCls: "border-red-200", bgCls: "bg-red-50" },
  agreement: { label: "APPROVED", textCls: "text-emerald-700", borderCls: "border-emerald-200", bgCls: "bg-emerald-50" },
}

export function AgentCard({ proposal, index }: { proposal: AgentProposal; index: number }) {
  const config = AGENT_CONFIGS.find((c) => c.id === proposal.agentId)
  const [visibleSteps, setVisibleSteps] = useState(0)
  const [expanded, setExpanded] = useState(true)
  const stepsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!proposal.actions?.length) return
    setVisibleSteps(0)
    let step = 0
    const interval = setInterval(() => {
      step++
      setVisibleSteps(step)
      if (step >= proposal.actions.length) clearInterval(interval)
    }, 400)
    return () => clearInterval(interval)
  }, [proposal.actions, proposal.round])

  useEffect(() => {
    if (stepsRef.current) {
      stepsRef.current.scrollTop = stepsRef.current.scrollHeight
    }
  }, [visibleSteps])

  if (!config) return null

  const isAgreed = proposal.status === "agreed"
  const isObjecting = proposal.status === "objecting"

  return (
    <div
      className="rounded-xl border overflow-hidden animate-float-in bg-card shadow-sm"
      style={{
        animationDelay: `${index * 0.08}s`,
        borderColor: `color-mix(in srgb, ${config.color} 25%, #e5e7eb)`,
      }}
    >
      {/* Colored top bar */}
      <div className="h-[3px]" style={{ background: config.color }} />

      {/* Agent header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: `${config.color}12`, border: `1.5px solid ${config.color}30` }}
          >
            <span className="text-xs font-mono font-black" style={{ color: config.color }}>
              {config.name.slice(0, 2).toUpperCase()}
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-foreground">{config.name}</span>
              <Badge
                variant="outline"
                className="text-[8px] px-1.5 py-0 font-mono font-bold"
                style={{
                  borderColor: isAgreed ? "#10b981" : isObjecting ? "#ef4444" : `${config.color}50`,
                  color: isAgreed ? "#059669" : isObjecting ? "#dc2626" : config.color,
                  backgroundColor: isAgreed ? "#ecfdf5" : isObjecting ? "#fef2f2" : `${config.color}08`,
                }}
              >
                {proposal.status.toUpperCase()}
              </Badge>
            </div>
            <span className="text-[10px] text-muted-foreground">{config.role} -- R{proposal.round}</span>
          </div>
        </div>

        {/* Compact metrics */}
        <div className="flex items-center gap-3">
          {Object.entries(proposal.metrics).slice(0, 2).map(([key, val]) => (
            <div key={key} className="text-right">
              <span className="block text-[8px] text-muted-foreground uppercase">{key}</span>
              <span className="block text-[11px] font-mono font-bold" style={{ color: config.color }}>{val}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Toggle for execution log */}
      {proposal.actions && proposal.actions.length > 0 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-4 py-1.5 bg-secondary/50 border-t border-border text-[10px] font-mono text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        >
          <span className="uppercase tracking-widest font-semibold">
            Execution Log -- {proposal.actions.length} steps
          </span>
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      )}

      {/* Action steps */}
      {expanded && proposal.actions && proposal.actions.length > 0 && (
        <div ref={stepsRef} className="px-3 py-3 flex flex-col gap-2 max-h-[300px] overflow-y-auto bg-secondary/20">
          {proposal.actions.map((action, stepIdx) => {
            if (stepIdx >= visibleSteps) return null
            return <ActionStepBlock key={stepIdx} action={action} agentColor={config.color} stepIdx={stepIdx} />
          })}

          {visibleSteps < proposal.actions.length && (
            <div className="flex items-center gap-2 py-2 px-3">
              <Loader2 className="w-3 h-3 animate-spin" style={{ color: config.color }} />
              <span className="text-[10px] font-mono text-muted-foreground animate-pulse">Processing...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ActionStepBlock({ action, agentColor, stepIdx }: { action: ActionStep; agentColor: string; stepIdx: number }) {
  const style = STEP_STYLES[action.kind]
  const Icon = STEP_ICONS[action.kind]
  const isTerminal = action.kind === "tool_call" || action.kind === "tool_result"

  return (
    <div
      className={`rounded-lg border overflow-hidden animate-float-in ${style.borderCls}`}
      style={{ animationDelay: `${stepIdx * 0.05}s` }}
    >
      {/* Step header */}
      <div className={`flex items-center gap-2 px-3 py-1.5 ${style.bgCls}`}>
        <Icon className={`w-3 h-3 ${style.textCls}`} />
        <span className={`text-[9px] font-mono font-bold tracking-wider ${style.textCls}`}>{style.label}</span>
        <code className={`text-[10px] font-mono ml-1 ${style.textCls} opacity-75`}>{action.label}</code>
      </div>

      {/* Content */}
      <div className={`px-3 py-2 ${isTerminal ? "bg-card font-mono" : "bg-card"}`}>
        <p className={`text-[11px] leading-relaxed text-foreground/80 ${isTerminal ? "font-mono" : ""}`}>
          {isTerminal && <span className={`${style.textCls} opacity-50 select-none`}>{action.kind === "tool_call" ? "> " : "< "}</span>}
          {action.detail}
        </p>

        {action.data && Object.keys(action.data).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(action.data).map(([k, v]) => (
              <span
                key={k}
                className={`inline-flex items-center gap-1 text-[9px] font-mono px-2 py-0.5 rounded-md border ${style.borderCls} ${style.bgCls}`}
              >
                <span className="text-muted-foreground">{k}:</span>
                <span className={`font-bold ${style.textCls}`}>{v}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
