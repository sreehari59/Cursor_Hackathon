"use client"

import Image from "next/image"
import type { AgentId, AgentProposal, ConsensusResult, Order } from "@/lib/synk/types"
import { AGENT_CONFIGS } from "@/lib/synk/types"
import { Badge } from "@/components/ui/badge"
import { CheckCircle2, XCircle, Shield, TrendingUp } from "lucide-react"

const AGENT_AVATARS: Record<string, string> = {
  production: "/agents/production.jpg",
  finance: "/agents/finance.jpg",
  logistics: "/agents/logistics.jpg",
  procurement: "/agents/procurement.jpg",
  sales: "/agents/sales.jpg",
}

interface ConsensusCardProps {
  consensus: ConsensusResult
  order: Order
  finalProposals?: AgentProposal[]
}

export function ConsensusCard({ consensus, order, finalProposals = [] }: ConsensusCardProps) {
  const approved = consensus.approved
  const proposalMap = new Map(finalProposals.map((proposal) => [proposal.agentId, proposal]))
  const rejectedAgents = finalProposals.filter((proposal) => !proposal.approved)

  return (
    <div className={`rounded-2xl overflow-hidden bg-card border-2 shadow-xl animate-float-in ${
      approved ? "border-emerald-200 shadow-emerald-100/50" : "border-red-200 shadow-red-100/50"
    }`}>
      <div className={`flex items-center justify-between px-6 py-5 ${approved ? "bg-emerald-50" : "bg-red-50"}`}>
        <div className="flex items-center gap-3">
          {approved ? (
            <div className="w-11 h-11 rounded-xl bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            </div>
          ) : (
            <div className="w-11 h-11 rounded-xl bg-red-100 flex items-center justify-center">
              <XCircle className="w-6 h-6 text-red-600" />
            </div>
          )}
          <div>
            <span className="text-lg font-bold text-foreground block">
              {approved ? "Consensus Reached" : "Order Rejected"}
            </span>
            <span className="text-xs text-muted-foreground">All agents have finalized their positions</span>
          </div>
        </div>
        <Badge variant="outline" className={`text-xs font-bold px-3.5 py-1.5 rounded-full ${
          approved ? "border-emerald-300 text-emerald-700 bg-emerald-100" : "border-red-300 text-red-700 bg-red-100"
        }`}>
          {consensus.confidence}% Confidence
        </Badge>
      </div>

      <div className="px-6 py-5 grid grid-cols-3 gap-3">
        <MetricBox label="Final Price" value={`$${consensus.finalPrice.toFixed(2)}/unit`} color="#10b981" icon={<TrendingUp className="w-3.5 h-3.5" />} />
        <MetricBox label="Delivery" value={`${consensus.finalDeliveryDays} days`} color="#f59e0b" />
        <MetricBox label="Margin" value={`${consensus.finalMargin.toFixed(1)}%`} color="#3b82f6" />
        <MetricBox label="Shipping" value={consensus.shippingMode.charAt(0).toUpperCase() + consensus.shippingMode.slice(1)} color="#f59e0b" />
        <MetricBox label="Supplier" value={consensus.supplier} color="#8b5cf6" />
        <MetricBox label="Risk Score" value={consensus.riskScore}
          color={consensus.riskScore === "Low" ? "#16a34a" : consensus.riskScore === "Medium" ? "#ca8a04" : "#dc2626"} />
      </div>

      <div className="mx-6 mb-4 flex items-center justify-between px-5 py-3.5 rounded-xl bg-secondary border border-border">
        <span className="text-sm font-medium text-muted-foreground">Total Deal Value</span>
        <span className="text-xl font-mono font-bold text-foreground">
          ${(consensus.finalPrice * order.quantity).toLocaleString()}
        </span>
      </div>

      <div className="px-6 pb-4">
        <div className="flex items-center gap-2 mb-2.5">
          <Shield className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Agent Decisions</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {AGENT_CONFIGS.map((agent) => {
            const proposal = proposalMap.get(agent.id)
            const agentApproved = proposal ? proposal.approved : approved
            const statusLabel = proposal?.status ? proposal.status.toUpperCase() : agentApproved ? "AGREED" : "OBJECTING"

            return (
              <div
                key={agent.id}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${
                  agentApproved ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"
                }`}
              >
                <div className="w-6 h-6 rounded-full overflow-hidden">
                  <Image src={AGENT_AVATARS[agent.id as AgentId] || ""} alt={agent.name} width={24} height={24} className="object-cover w-full h-full" />
                </div>
                <span className="text-xs font-medium text-foreground">{agent.name}</span>
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${
                  agentApproved ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                }`}>
                  {statusLabel}
                </span>
                {agentApproved ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-red-500" />
                )}
              </div>
            )
          })}
        </div>
        {!approved && rejectedAgents.length > 0 && (
          <p className="mt-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
            Rejected by: {rejectedAgents.map((proposal) => AGENT_CONFIGS.find((agent) => agent.id === proposal.agentId)?.name || proposal.agentId).join(", ")}
          </p>
        )}
      </div>

      <div className="px-6 pb-5">
        <p className="text-sm text-muted-foreground leading-relaxed bg-secondary rounded-xl px-4 py-3 border border-border">
          {consensus.summary}
        </p>
      </div>
    </div>
  )
}

function MetricBox({ label, value, color, icon }: { label: string; value: string; color: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col px-3.5 py-3 rounded-xl bg-secondary border border-border">
      <div className="flex items-center gap-1.5 mb-1">
        {icon && <span style={{ color }}>{icon}</span>}
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">{label}</span>
      </div>
      <span className="text-sm font-mono font-bold" style={{ color }}>{value}</span>
    </div>
  )
}
