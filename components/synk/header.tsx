"use client"

import Image from "next/image"
import type { DemoPhase } from "@/lib/synk/types"

const PHASE_LABELS: Record<DemoPhase, string> = {
  idle: "Ready",
  "incoming-call": "Incoming Call",
  "active-call": "Call Active",
  "order-broadcast": "Broadcasting Order",
  "round-1": "Negotiation Round 1",
  "round-2": "Negotiation Round 2",
  "round-3": "Negotiation Round 3",
  consensus: "Building Consensus",
  callback: "Customer Callback",
  done: "Complete",
}

type BackendSource = "unknown" | "backend" | "frontend-fallback"

interface SynkHeaderProps {
  phase: DemoPhase
  backendSource: BackendSource
  backendMessage?: string
}

export function SynkHeader({ phase, backendSource, backendMessage }: SynkHeaderProps) {
  const isActive = phase !== "idle" && phase !== "done"
  const isNegotiating = phase.startsWith("round-")

  return (
    <header className="flex items-center justify-between border-b border-border px-6 py-2.5 bg-card">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center overflow-hidden">
          <Image src="/agents/orchestrator.jpg" alt="SYNK" width={32} height={32} className="object-cover w-full h-full" />
        </div>
        <div>
          <h1 className="text-sm font-bold tracking-wider text-foreground font-mono">SYNK</h1>
          <p className="text-[9px] text-muted-foreground tracking-[0.15em] uppercase">Multi-Agent Manufacturing Intelligence</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div
          className={`flex items-center gap-2 px-3 py-1 rounded-full border ${
            backendSource === "backend"
              ? "bg-emerald-50 border-emerald-200"
              : backendSource === "frontend-fallback"
                ? "bg-amber-50 border-amber-200"
                : "bg-secondary border-border"
          }`}
          title={backendMessage || ""}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              backendSource === "backend"
                ? "bg-emerald-500"
                : backendSource === "frontend-fallback"
                  ? "bg-amber-500"
                  : "bg-muted-foreground/30"
            }`}
          />
          <span className="text-[11px] font-medium text-foreground">
            {backendSource === "backend"
              ? "Backend Connected"
              : backendSource === "frontend-fallback"
                ? "Frontend Dummy Mode"
                : "Backend Status Unknown"}
          </span>
        </div>

        <div className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full border transition-colors ${
          isNegotiating ? "bg-primary/5 border-primary/20" : phase === "consensus" ? "bg-emerald-50 border-emerald-200" : phase === "done" ? "bg-emerald-50 border-emerald-200" : "bg-secondary border-border"
        }`}>
          <span className={`w-2 h-2 rounded-full ${
            isNegotiating ? "bg-primary animate-pulse" : phase === "done" ? "bg-emerald-500" : isActive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/30"
          }`} />
          <span className="text-[11px] font-medium text-foreground">{PHASE_LABELS[phase]}</span>
        </div>
      </div>
    </header>
  )
}
