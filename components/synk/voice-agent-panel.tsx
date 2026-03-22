"use client"

import Image from "next/image"
import { CheckCircle2, Clock, Package, Phone, Plus, XCircle } from "lucide-react"
import type { DemoPhase, Order, ConsensusResult } from "@/lib/synk/types"
import type { CallLog } from "@/app/page"
import { VoiceWaveform } from "./voice-waveform"
import { VoiceTranscript, type TranscriptMessage } from "./voice-transcript"
import { OrderCard } from "./order-card"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { APPROVED_ORDER_EXAMPLE, DEFAULT_ORDER } from "@/lib/synk/scenario"

interface VoiceAgentPanelProps {
  phase: DemoPhase
  order: Order
  voiceOrderReady: boolean
  voiceStatusMessage: string | null
  liveAudioStatus: string | null
  transcript: TranscriptMessage[]
  consensus: ConsensusResult | null
  callHistory: CallLog[]
  onAcceptCall: () => void
  onOrderChange: (order: Order) => void
  onSubmitOrder: () => void
  onNewCall: () => void
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export function VoiceAgentPanel({
  phase,
  order,
  voiceOrderReady,
  voiceStatusMessage,
  liveAudioStatus,
  transcript,
  consensus,
  callHistory,
  onAcceptCall,
  onOrderChange,
  onSubmitOrder,
  onNewCall,
}: VoiceAgentPanelProps) {
  const isCallActive = phase === "active-call" || phase === "callback"
  const isProcessing = ["order-broadcast", "round-1", "round-2", "round-3", "consensus"].includes(phase)
  const isCallback = phase === "callback"
  const isDone = phase === "done"
  const showVoiceBand = phase !== "idle" && !isDone
  const showOrderSummary = phase !== "idle"
  const isOrderEditable = phase === "active-call"
  const displayCustomer = order.customer || "Awaiting capture"
  const orderStatusText =
    voiceStatusMessage ||
    (isProcessing
      ? "Order submitted to agent network. Keeping the captured details visible during orchestration."
      : isCallback
        ? "Decision callback in progress. Order details remain available for reference."
        : isDone
          ? "Run complete. Final order details are shown below."
          : "Waiting for outbound voice result.")

  return (
    <div className="flex flex-col h-full bg-card relative">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <Image src="/agents/voice-agent.jpg" alt="Voice Agent" width={32} height={32} className="rounded-full ring-2 ring-primary/20" />
          <div>
            <span className="text-sm font-semibold text-foreground">SYNK Voice Agent</span>
            <span className="block text-[10px] text-muted-foreground">AI-powered order intake</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isCallActive && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-600 text-[10px] font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Connected
            </span>
          )}
          {isProcessing && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-[10px] font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              Processing
            </span>
          )}
          {isDone && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary text-secondary-foreground text-[10px] font-semibold">
              Ready
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {phase === "idle" && (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex flex-col items-center justify-center gap-8 px-6 py-10 shrink-0">
              <div className="relative">
                <div className="w-36 h-36 rounded-full bg-gradient-to-br from-indigo-100 via-purple-50 to-blue-100 flex items-center justify-center shadow-xl shadow-indigo-100/50">
                  <div className="w-28 h-28 rounded-full overflow-hidden ring-4 ring-white shadow-inner">
                    <Image src="/agents/voice-agent.jpg" alt="Voice Agent" width={112} height={112} className="object-cover w-full h-full" />
                  </div>
                </div>
                <div className="absolute -bottom-2 left-1/2 -translate-x-1/2">
                  <button
                    onClick={onAcceptCall}
                    className="w-12 h-12 rounded-full bg-foreground text-card flex items-center justify-center shadow-lg hover:scale-105 transition-transform cursor-pointer"
                  >
                    <Phone className="w-5 h-5" />
                  </button>
                </div>
              </div>
              <div className="text-center">
                <p className="text-base font-semibold text-foreground">Start system</p>
                <p className="text-sm text-muted-foreground mt-1">Trigger outbound voice capture and prepare the agent-network order</p>
              </div>
            </div>

            {callHistory.length > 0 && (
              <div className="flex-1 min-h-0 border-t border-border">
                <div className="px-4 py-2.5">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Recent Calls</span>
                </div>
                <ScrollArea className="h-full px-2">
                  <div className="space-y-0.5 pb-4">
                    {callHistory.map((log) => (
                      <CallLogRow key={log.id} log={log} />
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}
          </div>
        )}

        {(isCallActive || isProcessing) && !isDone && (
          <div className="flex-1 flex flex-col overflow-hidden">
            {showVoiceBand && (
              <div className="px-5 py-3 border-b border-border bg-secondary/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                    {isCallback ? "Calling back" : "System active"} -- {displayCustomer}
                  </span>
                </div>
                <VoiceWaveform active={isCallActive || isProcessing} />
              </div>
            )}

            {isProcessing && (
              <div className="px-5 py-3 border-b border-border bg-primary/[0.03]">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <div className="w-3.5 h-3.5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-foreground">Running Agent Orchestration</p>
                    <p className="text-[11px] text-muted-foreground">
                      {phase === "order-broadcast" ? "Broadcasting order..." : phase === "consensus" ? "Building consensus..." : `Negotiation ${phase.replace("round-", "Round ")} in progress...`}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {showOrderSummary && (
              <div className="px-5 py-3 border-b border-border">
                <OrderCard order={order} editable={isOrderEditable} onOrderChange={isOrderEditable ? onOrderChange : undefined} />
                {phase === "active-call" && (
                  <>
                    <div className="mt-3 flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="rounded-full text-xs"
                        onClick={() => onOrderChange({ ...DEFAULT_ORDER })}
                      >
                        Rejected Example
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="rounded-full text-xs"
                        onClick={() => onOrderChange({ ...APPROVED_ORDER_EXAMPLE })}
                      >
                        Approved Example
                      </Button>
                    </div>
                    <Button
                      onClick={onSubmitOrder}
                      disabled={!voiceOrderReady}
                      className="w-full mt-3 rounded-full font-medium"
                      size="sm"
                    >
                      {voiceOrderReady ? "Submit to Agent Network" : "Awaiting Voice Result"}
                    </Button>
                  </>
                )}
              </div>
            )}

            <div className="flex-1 overflow-hidden p-5">
              <VoiceTranscript messages={transcript} />
            </div>
          </div>
        )}

        {isDone && (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="px-5 py-4 border-b border-border">
              <OrderCard order={order} />
            </div>

            <div className="px-5 py-4 border-b border-border">
              <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl ${
                consensus?.approved ? "bg-emerald-50 border border-emerald-200" : "bg-red-50 border border-red-200"
              }`}>
                {consensus?.approved ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <XCircle className="w-4 h-4 text-red-600" />}
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-foreground">
                    {consensus?.approved ? "Call ended -- Order Approved" : "Customer informed -- Order Rejected"}
                  </span>
                  {consensus?.approved && (
                    <span className="block text-xs text-muted-foreground mt-0.5">
                      ${consensus.finalPrice}/unit -- {consensus.finalDeliveryDays}d delivery
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-col items-center gap-4 px-6 py-6 shrink-0">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center">
                <div className="w-14 h-14 rounded-full overflow-hidden ring-2 ring-white shadow-md">
                  <Image src="/agents/voice-agent.jpg" alt="Voice Agent" width={56} height={56} className="object-cover w-full h-full" />
                </div>
              </div>
              <p className="text-sm font-medium text-foreground">Agent ready for next run</p>
              <Button onClick={onNewCall} className="rounded-full font-medium px-6" size="sm">
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                New Run
              </Button>
            </div>

            {callHistory.length > 0 && (
              <div className="flex-1 min-h-0 border-t border-border">
                <div className="px-4 py-2.5">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Call Log</span>
                </div>
                <ScrollArea className="h-full px-2">
                  <div className="space-y-0.5 pb-4">
                    {callHistory.map((log) => (
                      <CallLogRow key={log.id} log={log} />
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}
          </div>
        )}
      </div>

      {isCallback && (
        <div className="absolute bottom-6 right-6 z-50 w-72 animate-pop-in">
          <div className="bg-card rounded-2xl shadow-2xl shadow-black/10 border border-border overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3 bg-secondary/50">
              <div className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-emerald-200">
                <Image src="/agents/voice-agent.jpg" alt="Voice Agent" width={40} height={40} className="object-cover w-full h-full" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Calling {order.customer}</p>
                <p className="flex items-center gap-1.5 text-[10px] text-emerald-600 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Connected
                </p>
              </div>
            </div>
            <div className="px-4 py-3">
              <VoiceWaveform active />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function CallLogRow({ log }: { log: CallLog }) {
  const isApproved = log.outcome === "approved"
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-secondary/50 transition-colors group cursor-default">
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isApproved ? "bg-emerald-50" : "bg-red-50"}`}>
        {isApproved ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <XCircle className="w-4 h-4 text-red-500" />}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-foreground truncate">{log.customer}</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${isApproved ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
            {isApproved ? "APPROVED" : "REJECTED"}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-0.5"><Package className="w-2.5 h-2.5" /> {log.product}</span>
          <span>x{log.quantity.toLocaleString()}</span>
          {log.finalPrice && <span>${log.finalPrice}/unit</span>}
        </div>
      </div>

      <div className="shrink-0 text-right">
        <span className="text-[10px] text-muted-foreground flex items-center gap-1">
          <Clock className="w-2.5 h-2.5" />
          {formatTime(log.timestamp)}
        </span>
      </div>
    </div>
  )
}
