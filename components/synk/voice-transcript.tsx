"use client"

import { useEffect, useRef } from "react"
import Image from "next/image"

export interface TranscriptMessage {
  id: string
  sender: "customer" | "agent"
  text: string
  timestamp?: string
}

export function VoiceTranscript({ messages }: { messages: TranscriptMessage[] }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  if (messages.length === 0) return null

  return (
    <div ref={scrollRef} className="flex flex-col gap-3 overflow-y-auto max-h-full px-1">
      {messages.map((msg, idx) => (
        <div
          key={msg.id}
          className={`flex ${msg.sender === "agent" ? "justify-start" : "justify-end"} animate-float-in`}
          style={{ animationDelay: `${idx * 0.03}s` }}
        >
          {msg.sender === "agent" && (
            <div className="w-7 h-7 rounded-full overflow-hidden mr-2 shrink-0 mt-1">
              <Image src="/agents/voice-agent.jpg" alt="Agent" width={28} height={28} className="object-cover w-full h-full" />
            </div>
          )}
          <div className={`max-w-[80%] px-4 py-2.5 text-sm leading-relaxed ${
            msg.sender === "agent"
              ? "bg-secondary rounded-2xl rounded-bl-md text-secondary-foreground"
              : "bg-foreground text-card rounded-2xl rounded-br-md"
          }`}>
            {msg.text}
          </div>
        </div>
      ))}
    </div>
  )
}
