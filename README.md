# Multi-Agent Negotiation Backend (LangGraph)

This backend serves the frontend negotiation UI using Flask and LangGraph-backed orchestration.

## Current API Base

`http://localhost:5000/api`

## Active Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Backend and LLM readiness check |
| POST | `/orders` | Frontend-compatible order submission |
| POST | `/rounds` | Build one negotiation round summary |
| POST | `/consensus` | Build final consensus from rounds |
| GET | `/orchestrate` | SSE stream for full multi-round flow |
| GET | `/agents` | List agent metadata and tools |
| GET | `/agents/<agent_id>` | Get one agent profile |
| POST | `/agents/<agent_id>/analyze` | Get one agent mock proposal |
| GET | `/baseline` | Return baseline operating constants |

## Run

```bash
cd kai_hackathon_1
.\venv\Scripts\activate
pip install -r requirements.txt
python api_langgraph.py
```

Server starts on `http://localhost:5000`.

## Frontend Integration Notes

- Frontend should call `/api/orders` for submit.
- Frontend SSE should use `/api/orchestrate?order=<urlencoded-json>`.
- If backend fails, frontend may fall back to dummy data and should surface that state in UI.

## Project Structure

```text
kai_hackathon_1/
  api_langgraph.py                # Flask entrypoint
  api_langgraph_app/
    __init__.py                   # App factory and blueprint registration
    state.py                      # Shared logger + LangGraph manager setup
    services.py                   # Core orchestration utilities
    constants.py                  # Baseline constants
    routes/                       # HTTP routes
      health.py
      orders.py
      negotiation.py
      agents.py
    agents/                       # Agent registry + per-agent tools/profiles
      registry.py
      runtime/                    # Real LangGraph runtime agent implementations
      production/
      finance/
      logistics/
      procurement/
      sales/
  data/                           # Inventory/material sample data
```

## Legacy Cleanup

Removed legacy files that are no longer part of the active backend contract:

- `api.py`
- `test_client.py`
- `Postman_Collection.json`

Use `api_langgraph.py` and `/api/*` routes only.
