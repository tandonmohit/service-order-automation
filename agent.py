import os
import json
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()  # loads .env from current directory

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

API_BASE = "http://localhost:8001"
MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """You are an IT Resource Service Order (SO) Assistant. Your GOAL is to help users create a complete and valid IT Resource Service Order by collecting all required information through a friendly, structured conversation. Once all data is gathered, you output a clean JSON object.

---

## PERSONA & TONE
- Be professional, concise, and helpful.
- Guide the user step-by-step without overwhelming them.
- Ask for one category of fields at a time.
- Validate inputs as you go and flag errors immediately.

---

## COLLECTION WORKFLOW

Collect fields in the following 4 groups, one group at a time. Wait for the user's response before moving to the next group.

---

### GROUP 1 — Project & Assignment
Ask for:
1. **Opportunity ID** — Unique identifier for the opportunity (e.g. OPP-2024-001).Allow only numbers
2. **Project ID / Name** — The project this resource is being assigned to
3. **Hiring Manager ID** — Employee ID or name of the hiring manager

---

### GROUP 2 — Assignment Details
Ask for:
4. **Requirement Type** — Type of requirement (e.g. New Hire, Backfill, Contract, Extension)
5. **Requirement Start Date** — Expected start date (format: DD-MMM-YYYY, e.g. 15-Jul-2025)
6. **Billability Role** — Role in terms of billing (e.g. Billable, Non-Billable, Bench)
7. **Customer Hourly Billing Rate** — Rate billed to the customer per hour (e.g. $85/hr)
8. **Customer Profitability (%)** — Expected profitability margin as a percentage (e.g. 25%)
9. **Revenue Potential Tag** — Revenue classification tag (e.g. High, Medium, Low or a specific tag used by your org)

---

### GROUP 3 — Location
Ask for:
10. **Is this a client location-based requirement?** — Yes or No
11. **Location** — City, Country, or office location (e.g. Chennai, India)
12. **Business Unit** — The business unit raising this requirement (e.g. Digital, Cloud, SAP)

---

### GROUP 4 — Skills
Ask for:
13. **SO Type** — Service Order type (e.g. Internal, External, Hybrid)
14. **Grade** — Resource grade/level (e.g. L3, L4, Senior Analyst, Lead)
15. **Demand Role** — The job role being demanded (e.g. Java Developer, Business Analyst, DevOps Engineer)
16. **Primary Skills** — Key technical/functional skills required (e.g. Java, Spring Boot, AWS — comma-separated)

---

## VALIDATION RULES
- **Opportunity ID**: Must be a non-empty string. Suggest format OPP-YYYY-NNN if user is unsure.
- **Requirement Start Date**: Must be a valid future date. Reject past dates with a warning.
- **Customer Hourly Billing Rate**: Must be a positive number. Ask for currency if not specified.
- **Customer Profitability (%)**: Must be a number between 0 and 100.
- **Is this a client location-based requirement?**: Accept only Yes/No (or Y/N).
- **Skills**: Must have at least one skill listed.
- All other fields: Must be non-empty strings.

If a value fails validation, explain why and ask the user to re-enter it before proceeding.

---

## CONFIRMATION STEP
Before generating the JSON, display a formatted summary of all 16 fields grouped by category and ask the user to confirm before submitting."""

tools = [
    {
        "name": "create_service_order",
        "description": "Create a new service order in the system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the service order"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what is needed"
                },
                "requester": {
                    "type": "string",
                    "description": "Full name of the person requesting the service"
                },
                "service_type": {
                    "type": "string",
                    "description": "Category of service (e.g. IT Support, Maintenance, HR, Facilities)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Priority level (default: medium)"
                }
            },
            "required": ["title", "description", "requester", "service_type"]
        }
    },
    {
        "name": "list_service_orders",
        "description": "List existing service orders, optionally filtered by status or priority.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "completed", "cancelled"],
                    "description": "Filter by order status"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Filter by priority"
                }
            }
        }
    }
]


def execute_tool(name: str, tool_input: dict) -> str:
    try:
        if name == "create_service_order":
            resp = requests.post(f"{API_BASE}/orders", json=tool_input, timeout=5)
            resp.raise_for_status()
            order = resp.json()
            return json.dumps({
                "success": True,
                "order_id": order["id"],
                "title": order["title"],
                "status": order["status"],
                "priority": order["priority"],
                "message": f"Service order created successfully with ID {order['id']}"
            })

        elif name == "list_service_orders":
            params = {k: v for k, v in tool_input.items() if v}
            resp = requests.get(f"{API_BASE}/orders", params=params, timeout=5)
            resp.raise_for_status()
            orders = resp.json()
            if not orders:
                return json.dumps({"orders": [], "count": 0, "message": "No orders found."})
            return json.dumps({"orders": orders, "count": len(orders)})

        return json.dumps({"error": f"Unknown tool: {name}"})

    except requests.exceptions.ConnectionError:
        return json.dumps({
            "error": "Cannot connect to the service order API. "
                     "Make sure the server is running: python main.py"
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(messages: list) -> tuple[str, list]:
    """Run the agentic loop for one user turn. Returns (response_text, updated_messages)."""
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text, messages

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool: {block.name}]")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": tool_results})
            # loop continues — feed results back to Claude


def main():
    print("=" * 50)
    print("  Service Order Agent")
    print("=" * 50)
    print("Chat with the agent to create or view service orders.")
    print("Type 'quit' or 'exit' to stop.\n")

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        return

    messages = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            response_text, messages = run_agent(messages)
            print(f"\nAgent: {response_text}\n")
        except anthropic.AuthenticationError:
            print("ERROR: Invalid ANTHROPIC_API_KEY.\n")
        except Exception as e:
            print(f"ERROR: {e}\n")
            messages.pop()  # remove the failed user message so conversation stays valid


if __name__ == "__main__":
    main()
