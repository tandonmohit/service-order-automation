from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uvicorn
import uuid
import json
import os
import anthropic as _anthropic

app = FastAPI(
    title="Service Order Automation API",
    description="API for creating and managing service orders",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store
orders: dict = {}


# --- Models ---

class ServiceOrderCreate(BaseModel):
    title: str
    description: str
    requester: str
    priority: str = "medium"  # low | medium | high
    service_type: str


class ServiceOrderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None  # open | in_progress | completed | cancelled


class ServiceOrder(BaseModel):
    id: str
    title: str
    description: str
    requester: str
    priority: str
    service_type: str
    status: str
    created_at: str
    updated_at: str


# --- Endpoints ---

@app.get("/")
async def root():
    return {
        "service": "Service Order Automation API",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "order_count": len(orders)}


@app.post("/orders", response_model=ServiceOrder, status_code=201)
async def create_order(payload: ServiceOrderCreate):
    now = datetime.now().isoformat()
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        title=payload.title,
        description=payload.description,
        requester=payload.requester,
        priority=payload.priority,
        service_type=payload.service_type,
        status="open",
        created_at=now,
        updated_at=now,
    )
    orders[order.id] = order
    return order


@app.get("/orders", response_model=List[ServiceOrder])
async def list_orders(status: Optional[str] = None, priority: Optional[str] = None):
    result = list(orders.values())
    if status:
        result = [o for o in result if o.status == status]
    if priority:
        result = [o for o in result if o.priority == priority]
    return result


@app.get("/orders/{order_id}", response_model=ServiceOrder)
async def get_order(order_id: str):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.patch("/orders/{order_id}", response_model=ServiceOrder)
async def update_order(order_id: str, payload: ServiceOrderUpdate):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = order.model_dump()
    for field, value in payload.model_dump(exclude_none=True).items():
        updated[field] = value
    updated["updated_at"] = datetime.now().isoformat()
    orders[order_id] = ServiceOrder(**updated)
    return orders[order_id]


@app.delete("/orders/{order_id}", status_code=204)
async def delete_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")
    del orders[order_id]


# --- Agent ---

_AGENT_SYSTEM = """You are a helpful service order assistant. Help users create and manage service orders.

When creating a service order, gather through conversation:
- Title (short summary)
- Description (what is needed)
- Requester (who is asking)
- Service type (e.g. IT Support, Maintenance, HR, Facilities)
- Priority (low / medium / high — default to medium)

Use the create_service_order tool once you have enough info. You can also list orders when asked."""

_AGENT_TOOLS = [
    {
        "name": "create_service_order",
        "description": "Create a new service order in the system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title"},
                "description": {"type": "string", "description": "Detailed description"},
                "requester": {"type": "string", "description": "Requester full name"},
                "service_type": {"type": "string", "description": "Service category"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]}
            },
            "required": ["title", "description", "requester", "service_type"]
        }
    },
    {
        "name": "list_service_orders",
        "description": "List existing service orders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "in_progress", "completed", "cancelled"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]}
            }
        }
    }
]

# session_id -> full Anthropic message history
_agent_sessions: dict = {}


def _run_tool(name: str, tool_input: dict) -> str:
    if name == "create_service_order":
        now = datetime.now().isoformat()
        order = ServiceOrder(
            id=str(uuid.uuid4()),
            title=tool_input["title"],
            description=tool_input["description"],
            requester=tool_input["requester"],
            service_type=tool_input["service_type"],
            priority=tool_input.get("priority", "medium"),
            status="open",
            created_at=now,
            updated_at=now,
        )
        orders[order.id] = order
        return json.dumps({
            "success": True,
            "order_id": order.id,
            "title": order.title,
            "status": order.status,
        })

    if name == "list_service_orders":
        result = list(orders.values())
        if tool_input.get("status"):
            result = [o for o in result if o.status == tool_input["status"]]
        if tool_input.get("priority"):
            result = [o for o in result if o.priority == tool_input["priority"]]
        return json.dumps({"orders": [o.model_dump() for o in result], "count": len(result)})

    return json.dumps({"error": f"Unknown tool: {name}"})


class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class AgentChatResponse(BaseModel):
    response: str
    session_id: str


@app.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(request: AgentChatRequest):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured on server")

    session_id = request.session_id or str(uuid.uuid4())
    messages = list(_agent_sessions.get(session_id, []))
    messages.append({"role": "user", "content": request.message})

    client = _anthropic.Anthropic(api_key=api_key)

    while True:
        resp = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=_AGENT_SYSTEM,
            tools=_AGENT_TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if b.type == "text"), "")
            _agent_sessions[session_id] = messages
            return AgentChatResponse(response=text, session_id=session_id)

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = _run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
