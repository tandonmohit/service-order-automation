from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

from agent import run_agent, client  # reuse agent logic

app = FastAPI()

# In-memory sessions: session_id -> message history
sessions: dict = {}

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Service Order Agent</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      min-height: 100vh;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem 1rem;
    }

    .card {
      background: white;
      border-radius: 20px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.2);
      width: 100%;
      max-width: 620px;
      padding: 2rem;
    }

    h1 {
      font-size: 1.5rem;
      color: #1f2937;
      margin-bottom: 0.25rem;
    }

    .subtitle {
      font-size: 0.9rem;
      color: #6b7280;
      margin-bottom: 1.75rem;
    }

    label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      color: #374151;
      margin-bottom: 0.4rem;
    }

    textarea {
      width: 100%;
      padding: 0.75rem 1rem;
      font-size: 0.95rem;
      font-family: inherit;
      border: 2px solid #e5e7eb;
      border-radius: 12px;
      outline: none;
      resize: vertical;
      transition: border-color 0.2s;
      background: #f9fafb;
      color: #111827;
    }

    textarea:focus { border-color: #667eea; background: white; }
    textarea:disabled { opacity: 0.6; cursor: not-allowed; }
    textarea[readonly] { background: #f3f4f6; cursor: default; }

    #message { min-height: 90px; }
    #response { min-height: 120px; color: #374151; }

    .actions {
      display: flex;
      gap: 0.75rem;
      margin: 1rem 0 1.5rem;
    }

    button {
      padding: 0.65rem 1.5rem;
      font-size: 0.95rem;
      font-weight: 600;
      border: none;
      border-radius: 10px;
      cursor: pointer;
      transition: opacity 0.2s, transform 0.1s;
    }

    button:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }

    #submitBtn {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      flex: 1;
    }

    #clearBtn {
      background: #e5e7eb;
      color: #374151;
    }

    .status {
      font-size: 0.82rem;
      color: #9ca3af;
      margin-top: 0.5rem;
      min-height: 1.2em;
    }

    .status.error { color: #ef4444; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Service Order Agent</h1>
    <p class="subtitle">Describe your request and the agent will create a service order.</p>

    <label for="message">Your message</label>
    <textarea id="message" placeholder="e.g. I need a new laptop for John Smith, high priority"></textarea>

    <div class="actions">
      <button id="submitBtn" onclick="sendMessage()">Send</button>
      <button id="clearBtn" onclick="clearAll()">New Chat</button>
    </div>

    <label for="response">Agent response</label>
    <textarea id="response" readonly placeholder="The agent's reply will appear here…"></textarea>
    <p class="status" id="status"></p>
  </div>

  <script>
    let sessionId = null;

    async function sendMessage() {
      const msgEl = document.getElementById('message');
      const respEl = document.getElementById('response');
      const statusEl = document.getElementById('status');
      const submitBtn = document.getElementById('submitBtn');

      const message = msgEl.value.trim();
      if (!message) return;

      submitBtn.disabled = true;
      msgEl.disabled = true;
      respEl.value = '';
      statusEl.textContent = 'Thinking…';
      statusEl.className = 'status';

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, session_id: sessionId })
        });

        const data = await res.json();

        if (!res.ok) {
          statusEl.textContent = data.detail || 'Error from agent.';
          statusEl.className = 'status error';
        } else {
          sessionId = data.session_id;
          respEl.value = data.response;
          msgEl.value = '';
          statusEl.textContent = 'Done.';
        }
      } catch (err) {
        statusEl.textContent = 'Network error: ' + err.message;
        statusEl.className = 'status error';
      } finally {
        submitBtn.disabled = false;
        msgEl.disabled = false;
        msgEl.focus();
      }
    }

    function clearAll() {
      sessionId = null;
      document.getElementById('message').value = '';
      document.getElementById('response').value = '';
      document.getElementById('status').textContent = '';
      document.getElementById('message').focus();
    }

    // Submit on Ctrl+Enter
    document.getElementById('message').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.ctrlKey) sendMessage();
    });
  </script>
</body>
</html>
"""


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/chat")
async def chat(req: ChatRequest):
    import uuid
    from fastapi import HTTPException

    session_id = req.session_id or str(uuid.uuid4())
    messages = list(sessions.get(session_id, []))
    messages.append({"role": "user", "content": req.message})

    try:
        response_text, messages = run_agent(messages)
        sessions[session_id] = messages
        return {"response": response_text, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("webapp:app", host="0.0.0.0", port=8080, reload=True)
