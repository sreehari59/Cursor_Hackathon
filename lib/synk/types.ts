// ─── SYNK Multi-Agent System Types ────────────────────────────────────────

export type AgentId = "production" | "finance" | "logistics" | "procurement" | "sales"

export type AgentStatus = "idle" | "analyzing" | "proposing" | "objecting" | "agreed"

export type DemoPhase =
  | "idle"
  | "incoming-call"
  | "active-call"
  | "order-broadcast"
  | "round-1"
  | "round-2"
  | "round-3"
  | "consensus"
  | "callback"
  | "done"

export type ShippingMode = "ground" | "express" | "air"

export interface Order {
  id: string
  customer: string
  product: string
  quantity: number
  requestedPrice: number
  requestedDeliveryDays: number
  priority: "standard" | "rush" | "critical"
}

// Step-by-step actions that each agent performs
export type ActionStepKind = "tool_call" | "tool_result" | "thinking" | "response" | "objection" | "agreement"

export interface ActionStep {
  kind: ActionStepKind
  label: string        // e.g. "check_capacity()", "query_supplier_lead_time()"
  detail: string       // e.g. "5,000 units require 7 production days..."
  data?: Record<string, string | number>  // structured data to display
}

export interface AgentProposal {
  agentId: AgentId
  round: number
  status: AgentStatus
  reasoning: string
  metrics: Record<string, string | number>
  approved: boolean
  actions: ActionStep[]  // the step-by-step chain of what the agent did
}

export interface RoundSummary {
  round: number
  price: number
  deliveryDays: number
  margin: number
  shippingMode: ShippingMode
  overtimeHours: number
  proposals: AgentProposal[]
  converged: boolean
}

export interface ConsensusResult {
  approved: boolean
  finalPrice: number
  finalDeliveryDays: number
  finalMargin: number
  shippingMode: ShippingMode
  riskScore: "Low" | "Medium" | "High"
  confidence: number
  supplier: string
  overtimeHours: number
  summary: string
}

// Inter-agent negotiation messages
export interface AgentMessage {
  id: string
  from: AgentId | "orchestrator"
  to: AgentId | "orchestrator" | "all"
  round: number
  type: "proposal" | "objection" | "counter" | "agreement" | "info" | "directive"
  message: string
  timestamp: number
}

// SSE event types
export type SSEEventType =
  | "backend_status"
  | "phase_change"
  | "agent_update"
  | "agent_message"
  | "round_complete"
  | "consensus_reached"
  | "callback_start"
  | "callback_message"
  | "done"

export interface SSEEvent {
  type: SSEEventType
  data: {
    backendSource?: "backend" | "frontend-fallback"
    backendMessage?: string
    phase?: DemoPhase
    agentId?: AgentId
    proposal?: AgentProposal
    agentMessage?: AgentMessage
    roundSummary?: RoundSummary
    consensus?: ConsensusResult
    message?: string
  }
}

export interface AgentConfig {
  id: AgentId
  name: string
  role: string
  color: string
  icon: string
}

export const AGENT_CONFIGS: AgentConfig[] = [
  { id: "production", name: "Production", role: "Manufacturing & Scheduling", color: "#3b82f6", icon: "Factory" },
  { id: "finance", name: "Finance", role: "Margins & Pricing", color: "#10b981", icon: "DollarSign" },
  { id: "logistics", name: "Logistics", role: "Shipping & Delivery", color: "#f59e0b", icon: "Truck" },
  { id: "procurement", name: "Procurement", role: "Materials & Suppliers", color: "#8b5cf6", icon: "Package" },
  { id: "sales", name: "Sales", role: "Customer Relations", color: "#ef4444", icon: "Users" },
]
