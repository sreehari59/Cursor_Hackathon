"use client"

import type { RoundSummary, DemoPhase } from "@/lib/synk/types"
import { ArrowDown, ArrowUp, Minus } from "lucide-react"

interface NegotiationTimelineProps {
  rounds: RoundSummary[]
  currentPhase: DemoPhase
}

const ROUND_LABELS = ["Round 1", "Round 2", "Round 3", "Consensus"]

function ChangeIndicator({ prev, curr, invert }: { prev: number; curr: number; invert?: boolean }) {
  if (prev === curr) return <Minus className="w-2.5 h-2.5 text-muted-foreground" />
  const isUp = curr > prev
  const isGood = invert ? !isUp : isUp
  if (isGood) return <ArrowUp className="w-2.5 h-2.5 text-emerald-600" />
  return <ArrowDown className="w-2.5 h-2.5 text-red-500" />
}

export function NegotiationTimeline({ rounds, currentPhase }: NegotiationTimelineProps) {
  const currentRoundNum =
    currentPhase === "round-1" ? 1
      : currentPhase === "round-2" ? 2
        : currentPhase === "round-3" ? 3
          : currentPhase === "consensus" || currentPhase === "callback" || currentPhase === "done" ? 4
            : 0

  return (
    <div className="px-4 py-3">
      {/* Progress bar */}
      <div className="flex items-center gap-1.5 mb-4">
        {ROUND_LABELS.map((label, i) => {
          const roundNum = i + 1
          const isActive = roundNum === currentRoundNum
          const isDone = roundNum < currentRoundNum

          return (
            <div key={label} className="flex-1 flex flex-col items-center gap-1.5">
              <div className="flex items-center w-full gap-1">
                <div
                  className={`w-2.5 h-2.5 rounded-full shrink-0 transition-all duration-500 ${
                    isDone ? "bg-emerald-500 shadow-sm"
                      : isActive ? "bg-primary shadow-sm animate-pulse"
                        : "bg-muted"
                  }`}
                />
                <div
                  className={`flex-1 h-1 rounded-full transition-all duration-700 ${
                    isDone ? "bg-emerald-200"
                      : isActive ? "bg-primary/30"
                        : "bg-muted"
                  }`}
                />
              </div>
              <span
                className={`text-[9px] font-mono transition-colors ${
                  isDone ? "text-emerald-600 font-semibold"
                    : isActive ? "text-primary font-semibold"
                      : "text-muted-foreground/40"
                }`}
              >
                {roundNum === 4 ? "Final" : label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Parameter evolution table */}
      {rounds.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden bg-card">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="border-b border-border bg-secondary/50">
                <th className="text-left px-3 py-1.5 text-muted-foreground font-mono font-medium">Param</th>
                {rounds.map((r) => (
                  <th key={r.round} className="text-center px-2 py-1.5 text-muted-foreground font-mono font-medium">
                    R{r.round}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                { label: "Price", values: rounds.map(r => `$${r.price.toFixed(2)}`), rawValues: rounds.map(r => r.price), color: "#059669" },
                { label: "Delivery", values: rounds.map(r => `${r.deliveryDays}d`), rawValues: rounds.map(r => r.deliveryDays), color: "#d97706", invert: true },
                { label: "Margin", values: rounds.map(r => `${r.margin.toFixed(1)}%`), rawValues: rounds.map(r => r.margin), color: "#2563eb" },
                { label: "OT Hours", values: rounds.map(r => `${r.overtimeHours}h`), rawValues: rounds.map(r => r.overtimeHours), color: "#7c3aed", invert: true },
                { label: "Shipping", values: rounds.map(r => r.shippingMode.charAt(0).toUpperCase() + r.shippingMode.slice(1)), rawValues: rounds.map(() => 0), color: "#d97706", isText: true },
              ].map(({ label, values, rawValues, color, invert, isText }) => (
                <tr key={label} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-1.5 text-muted-foreground font-mono">{label}</td>
                  {values.map((v, i) => (
                    <td key={i} className="text-center px-2 py-1.5">
                      <div className="flex items-center justify-center gap-1">
                        <span className="font-mono font-semibold" style={{ color }}>{v}</span>
                        {i > 0 && !isText && (
                          <ChangeIndicator prev={rawValues[i - 1]} curr={rawValues[i]} invert={invert} />
                        )}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
