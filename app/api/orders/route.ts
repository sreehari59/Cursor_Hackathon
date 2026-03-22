import { NextResponse } from "next/server"
import type { Order } from "@/lib/synk/types"

export async function POST(request: Request) {
  const body = await request.json()
  const order: Order = {
    id: `ORD-RUSH-${String(Date.now()).slice(-3)}`,
    customer: body.customer || "Acme Corp",
    product: body.product || "PMP-STD-100",
    quantity: body.quantity || 50,
    requestedPrice: body.requestedPrice || 10.0,
    requestedDeliveryDays: body.requestedDeliveryDays || 18,
    priority: body.priority || "rush",
  }

  return NextResponse.json({ success: true, order })
}

