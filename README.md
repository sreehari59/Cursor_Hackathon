# ForgeAlign — Agent-to-Agent Orchestration Frontend

ForgeAlign is an intelligent multi-agent orchestration platform for manufacturing order fulfillment. Five specialized AI agents collaborate in real-time through structured negotiation rounds to evaluate, negotiate, and reach consensus on complex manufacturing orders — all visible through a live interactive dashboard.

Link to the Application: [ForgeAlign](https://cursor-hackathon-tawny.vercel.app/) 

![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss)

---

## Overview

ForgeAlign demonstrates the **Agent-to-Agent (A2A)** protocol where autonomous agents negotiate without human intervention. A simulated customer call triggers an order, which is broadcast to five domain-specific agents. Each agent analyzes the order through its own lens, raises objections, proposes counter-offers, and iterates over multiple rounds until consensus is reached.

### The Five Agents

| Agent | Domain | Role |
|-------|--------|------|
| **Production** | Manufacturing & Scheduling | Evaluates capacity, overtime needs, and production feasibility |
| **Finance** | Margins & Pricing | Enforces margin floors, computes unit economics, negotiates pricing |
| **Logistics** | Shipping & Delivery | Evaluates shipping modes (ground/express/air) and delivery timelines |
| **Procurement** | Materials & Suppliers | Queries supplier availability, lead times, and material costs |
| **Sales** | Customer Relations | Considers account value, relationship history, and timeline flexibility |

### Demo Flow

```
Idle → Incoming Call → Active Call → Order Broadcast → Round 1 → Round 2 → Round 3 → Consensus → Callback → Done
```

1. **Incoming Call** — A simulated voice call arrives from a customer
2. **Order Capture** — Order details are parsed from the conversation (product SKU, quantity, price, delivery)
3. **Order Broadcast** — The order is sent to all five agents simultaneously
4. **Negotiation Rounds** — Agents analyze, propose, object, and counter-propose across up to 3 rounds
5. **Consensus** — A final decision is synthesized (approve/reject) with confidence score and risk assessment
6. **Callback** — Results are communicated back to the customer

---

## Tech Stack

- **Framework:** Next.js 16 (App Router)
- **Language:** TypeScript 5.7
- **UI:** React 19, Radix UI, shadcn/ui
- **Styling:** Tailwind CSS 4
- **Charts:** Recharts
- **Forms:** React Hook Form + Zod
- **Streaming:** Server-Sent Events (SSE) for real-time agent updates
- **Package Manager:** pnpm

---

## Getting Started

### Prerequisites

- Node.js 18+
- pnpm

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Cursor_Hackathon

# Install dependencies
pnpm install
```

### Development

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### Production Build

```bash
pnpm build
pnpm start
```

---

## Project Structure

```
app/
├── page.tsx                    # Main orchestration dashboard
├── layout.tsx                  # Root layout with theme provider
├── globals.css                 # Global styles
└── api/
    ├── agents/                 # Agent listing & individual analysis
    │   └── [agentId]/
    │       └── analyze/        # Single-agent order analysis
    ├── orders/                 # Order creation & validation
    ├── rounds/                 # Execute negotiation rounds
    ├── consensus/              # Synthesize final consensus
    ├── orchestrate/            # Full orchestration via SSE stream
    ├── baseline/               # Operational baseline parameters
    └── voice-agent/            # Voice call simulation
        ├── start/              # Initiate voice call
        ├── latest/             # Latest voice agent response
        └── latest-transcript/  # Call transcript

components/
├── synk/
│   ├── header.tsx              # Top navigation bar with phase indicator
│   ├── voice-agent-panel.tsx   # Call handling, transcript, order capture
│   ├── orchestration-panel.tsx # Central agent network visualization
│   ├── agent-network.tsx       # Hexagonal graph of agents + orchestrator
│   ├── agent-card.tsx          # Per-agent proposal details (tools, reasoning)
│   ├── consensus-card.tsx      # Final approval/rejection result
│   ├── order-card.tsx          # Order details display
│   ├── negotiation-timeline.tsx# Round-by-round timeline
│   ├── agent-message-feed.tsx  # Real-time inter-agent message stream
│   ├── voice-transcript.tsx    # Incoming call transcript
│   └── voice-waveform.tsx      # Audio waveform visualization
└── ui/                         # shadcn/ui component library

lib/synk/
├── types.ts                    # Core type definitions (Order, AgentProposal, etc.)
├── agents.ts                   # Agent analysis logic (5 domain functions)
├── orchestrator.ts             # Round execution & consensus synthesis
├── scenario.ts                 # Demo data & voice scripts
├── baseline-data.ts            # Operational parameters & baselines
└── live-audio.ts               # Audio streaming utilities
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/agents` | List all agents with profiles and capabilities |
| `GET` | `/api/agents/:id` | Get a specific agent's operational parameters |
| `POST` | `/api/agents/:id/analyze` | Run single-agent analysis on an order |
| `POST` | `/api/orders` | Create and validate a new order |
| `POST` | `/api/rounds` | Execute one negotiation round across all agents |
| `POST` | `/api/consensus` | Synthesize consensus from completed rounds |
| `GET` | `/api/orchestrate` | Full orchestration flow via SSE stream |
| `GET` | `/api/baseline` | Retrieve operational baseline parameters |
| `POST` | `/api/voice-agent/start` | Initiate a voice agent call |
| `GET` | `/api/voice-agent/latest` | Get latest voice agent response |
| `GET` | `/api/voice-agent/latest-transcript` | Get latest call transcript |

Full API documentation is available via the Swagger spec at `public/swagger.yaml`.

---

## Key Features

- **Real-time SSE streaming** — Watch agents negotiate live with server-sent events
- **Interactive agent network** — Hexagonal visualization showing message flow between agents and the orchestrator
- **Multi-round negotiation** — Agents iterate through up to 3 rounds of proposals, objections, and counter-offers
- **Tool-use transparency** — Each agent's tool calls, results, and reasoning steps are fully visible
- **Voice agent simulation** — Simulated incoming customer calls with waveform visualization and transcripts
- **Order intelligence** — Automatic parsing of product SKUs, quantities, pricing, and delivery requirements from free-form text
- **Consensus engine** — Final decision synthesis with confidence scores, risk assessment, and margin analysis
- **Call history** — Logs of past orders with outcomes (approved/rejected)
- **Dark mode** — Full theme support via next-themes

---

## License

Private — All rights reserved.
