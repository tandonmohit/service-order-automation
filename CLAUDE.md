# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with:
```
ANTHROPIC_API_KEY=your-key-here
```

## Running the Services

The system has three independent entry points — run each in a separate terminal:

```bash
# Backend REST API (port 8001) — required before running agent or web UI
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Web chat UI (port 8080) — standalone, manages its own agent sessions
uvicorn webapp:app --host 0.0.0.0 --port 8080 --reload

# CLI interactive agent — requires backend running on port 8001
python agent.py
```

API docs available at `http://localhost:8001/docs` when backend is running.

## Architecture

### Components

**`main.py`** — FastAPI backend (port 8001). Owns all service order data in an in-memory `orders` dict (not persisted). Exposes CRUD endpoints plus `/agent/chat` for AI-driven order creation. Maintains per-session message history in `_agent_sessions`.

**`agent.py`** — CLI agent and shared agent logic. `ServiceOrderAgent` class implements a multi-turn agentic loop: sends messages + tools to Claude, handles `tool_use` stop reason by executing tools and feeding results back, loops until `end_turn`. The CLI agent calls `main.py`'s REST API to actually create/list orders.

**`webapp.py`** — FastAPI web UI (port 8080). Serves an inline HTML/CSS/JS chat page. Reuses the agent logic from `agent.py` and manages its own `sessions` dict independently of the backend.

### Agentic Loop Pattern

Both `main.py` and `agent.py` implement the same pattern:
1. Append user message to history
2. Call Claude (`claude-opus-4-6`) with `tools` + `thinking={"type": "adaptive"}`
3. If `stop_reason == "tool_use"`: execute the tool, append `tool_result` to history, go to step 2
4. If `stop_reason == "end_turn"`: return text response

Tools defined: `create_service_order`, `list_service_orders`.

### Service Order Fields

The CLI/web agent (`agent.py`) collects 16 required fields across 4 groups before creating an order:
- **Project & Assignment**: Opportunity ID, Project ID, Hiring Manager ID
- **Assignment Details**: Requirement Type, Start Date, Billability Role, Billing Rate, Profitability %, Revenue Tag
- **Location**: Client location flag, Location, Business Unit
- **Skills**: SO Type, Grade, Demand Role, Primary Skills

The backend agent (`main.py`) uses a simpler 5-field model: title, description, requester, service_type, priority.

### Data Models

Pydantic models in `main.py`:
- `ServiceOrderCreate` / `ServiceOrderUpdate` — input models
- `ServiceOrder` — full representation with UUID `id` and ISO timestamps
- `AgentChatRequest` / `AgentChatResponse` — `/agent/chat` contract

### CORS

Backend allows only `http://localhost:3000`. Update `allow_origins` in `main.py` if the web UI or other clients need access.
