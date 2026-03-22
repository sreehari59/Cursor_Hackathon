import type { Order } from "./types"

export const DEFAULT_ORDER: Order = {
  id: "ORD-RUSH-001",
  customer: "Acme Corp",
  product: "PMP-STD-100",
  quantity: 50,
  requestedPrice: 10.0,
  requestedDeliveryDays: 18,
  priority: "rush",
}

export const APPROVED_ORDER_EXAMPLE: Order = {
  id: "ORD-APPROVE-001",
  customer: "Acme Corp",
  product: "PMP-STD-100",
  quantity: 50,
  requestedPrice: 22.0,
  requestedDeliveryDays: 18,
  priority: "rush",
}

export const VOICE_SCRIPT = {
  incomingCall: {
    caller: "Acme Corp - Procurement Dept",
    callerNumber: "+1 (555) 234-7890",
  },
  customerMessages: [
    "Hi, this is Sarah from Acme Corp procurement.",
    "We need a rush order placed immediately -- 50 units of PMP-STD-100.",
    "We need delivery in 18 days max, and our target price is $10.00 per unit.",
    "This is for our Q3 product launch, so timing is critical.",
  ],
  agentResponses: [
    "Hello Sarah, thank you for calling SYNK Manufacturing.",
    "I'm capturing your order details now...",
    "Let me run this through our multi-agent optimization system to find the best fulfillment plan.",
    "I'll call you back shortly with our recommendation.",
  ],
  callbackMessages: [
    "Hello Sarah, I have your order analysis ready.",
    "Great news -- we can fulfill your rush order with a slight adjustment.",
    "We can deliver 50 units of PMP-STD-100 at $10.80 per unit within 19 days.",
    "This gives us a healthy margin while meeting your timeline with just one day of buffer.",
    "Our recommended shipping is ground freight, and materials are confirmed with ChemCorp Asia.",
    "Shall I confirm the order?",
  ],
  callbackMessagesRejected: [
    "Hello Sarah, I have your order analysis ready.",
    "Unfortunately, we are unable to fulfill the order at the requested terms.",
    "The combination of volume, timeline, and price point falls below our operational thresholds.",
    "I'd be happy to discuss alternative configurations that could work for both parties.",
  ],
}

