"""
Customer Data Agent - LLM-powered agent for database operations via MCP.
Uses GPT to decide which MCP tool to call and how to process results.
"""
import json
from typing import Any, Dict, List, Optional

import requests
from langchain_openai import ChatOpenAI


MCP_URL = "http://localhost:5001/mcp"

CUSTOMER_DATA_SYSTEM_PROMPT = """You are a Customer Data Agent responsible for database operations.

You have access to these MCP tools:
1. get_customer(customer_id) - Get customer info by ID
2. list_customers(status, limit) - List customers (status: "active" or "disabled")
3. update_customer(customer_id, data) - Update customer fields (email, phone, name, status)
4. create_ticket(customer_id, issue, priority) - Create support ticket
5. get_customer_history(customer_id) - Get all tickets for a customer

Based on the current state and data_op, decide:
1. Which tool(s) to call
2. What arguments to pass
3. How to interpret results

Output format (JSON only):
{
    "tool_calls": [
        {"tool": "tool_name", "args": {...}},
        ...
    ],
    "message_to_router": "Brief A2A message about what you did/found"
}

If data_op is null or unclear, return empty tool_calls and ask for clarification.
"""

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def _call_mcp_tool(name: str, arguments: Dict[str, Any], message_id: int = 1) -> Dict[str, Any]:
    """Call MCP server tool and parse response."""
    message = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments or {},
        },
    }

    try:
        resp = requests.post(
            MCP_URL,
            json=message,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=10,
        )

        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if not line_str.startswith("data: "):
                continue
            payload = json.loads(line_str[6:])
            if "result" in payload:
                content_list = payload["result"].get("content", [])
                if content_list and "text" in content_list[0]:
                    return json.loads(content_list[0]["text"])
            if "error" in payload:
                return {"success": False, "error": f"MCP error: {payload['error']}"}

        return {"success": False, "error": "Empty or invalid MCP response"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def customer_data_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM-powered Customer Data Agent.
    Uses LLM to decide which MCP tools to call based on the request.
    """
    new_state = dict(state)
    log: List[str] = list(new_state.get("log", []))

    data_op: Optional[str] = state.get("data_op")
    if not data_op:
        log.append("[CustomerData] No data operation requested, returning to Router.")
        new_state["next"] = "router"
        new_state["log"] = log
        return new_state

    # Build context for LLM
    context = {
        "data_op": data_op,
        "customer_id": new_state.get("customer_id"),
        "update_data": new_state.get("update_data"),
        "customers": new_state.get("customers", []),
        "new_ticket_issue": new_state.get("new_ticket_issue"),
        "new_ticket_priority": new_state.get("new_ticket_priority", "medium"),
    }

    messages = [
        {"role": "system", "content": CUSTOMER_DATA_SYSTEM_PROMPT},
        {"role": "user", "content": f"Execute this data operation:\n{json.dumps(context, indent=2)}"}
    ]

    result = _llm.invoke(messages)
    response_text = result.content.strip()

    # Parse LLM decision
    try:
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        decision = json.loads(response_text.strip())
    except json.JSONDecodeError:
        # Fallback: execute based on data_op directly
        decision = {"tool_calls": [], "message_to_router": "Parse error, using fallback"}
        decision["tool_calls"] = _get_fallback_tool_calls(data_op, new_state)

    # Execute tool calls
    for call in decision.get("tool_calls", []):
        tool_name = call.get("tool")
        args = call.get("args", {})
        
        log.append(f"[CustomerData] Calling MCP: {tool_name}({args})")
        result = _call_mcp_tool(tool_name, args)
        
        # Store results in state based on tool
        if result.get("success"):
            if tool_name == "get_customer":
                new_state["customer"] = result.get("customer")
                log.append(f"[CustomerData → Router] Got customer: {result.get('customer', {}).get('name')}")
            elif tool_name == "list_customers":
                new_state["customers"] = result.get("customers", [])
                log.append(f"[CustomerData → Router] Got {len(new_state['customers'])} customers")
            elif tool_name == "update_customer":
                new_state["customer"] = result.get("customer")
                log.append(f"[CustomerData → Router] Updated customer successfully")
            elif tool_name == "create_ticket":
                tickets = list(new_state.get("tickets", []))
                if "ticket" in result:
                    tickets.append(result["ticket"])
                new_state["tickets"] = tickets
                log.append(f"[CustomerData → Router] Created ticket #{result.get('ticket', {}).get('id')}")
            elif tool_name == "get_customer_history":
                new_state["tickets"] = result.get("tickets", [])
                log.append(f"[CustomerData → Router] Got {len(new_state['tickets'])} tickets")
        else:
            log.append(f"[CustomerData] MCP call failed: {result.get('error')}")

        new_state["last_data_result"] = result

    # Handle special composite operation
    if data_op == "get_high_priority_for_customers":
        customers = new_state.get("customers", [])
        tickets_by_customer = {}
        for c in customers:
            cid = c.get("id")
            if cid is None:
                continue
            result = _call_mcp_tool("get_customer_history", {"customer_id": cid})
            if result.get("success"):
                all_tickets = result.get("tickets", [])
                high_tickets = [t for t in all_tickets if t.get("priority") == "high"]
                if high_tickets:
                    tickets_by_customer[cid] = high_tickets
        
        new_state["tickets_by_customer"] = tickets_by_customer
        log.append(f"[CustomerData → Router] Got high-priority tickets for {len(tickets_by_customer)} customers")

    # A2A message from LLM
    if decision.get("message_to_router"):
        log.append(f"[CustomerData → Router] {decision['message_to_router']}")

    # Mark this data_op as completed to prevent loops
    completed_ops = list(new_state.get("completed_data_ops", []))
    if data_op and data_op not in completed_ops:
        completed_ops.append(data_op)
    new_state["completed_data_ops"] = completed_ops

    # Clear data_op and return to Router
    new_state["data_op"] = None
    new_state["next"] = "router"
    new_state["log"] = log
    return new_state


def _get_fallback_tool_calls(data_op: str, state: Dict[str, Any]) -> List[Dict]:
    """Fallback tool calls if LLM parsing fails."""
    customer_id = state.get("customer_id")
    update_data = state.get("update_data", {})
    
    if data_op == "get_customer" and customer_id:
        return [{"tool": "get_customer", "args": {"customer_id": customer_id}}]
    elif data_op == "get_customer_history" and customer_id:
        return [{"tool": "get_customer_history", "args": {"customer_id": customer_id}}]
    elif data_op == "list_active_customers":
        return [{"tool": "list_customers", "args": {"status": "active"}}]
    elif data_op == "update_customer" and customer_id and update_data:
        return [{"tool": "update_customer", "args": {"customer_id": customer_id, "data": update_data}}]
    elif data_op == "create_ticket" and customer_id:
        return [{"tool": "create_ticket", "args": {
            "customer_id": customer_id,
            "issue": state.get("new_ticket_issue", "Support request"),
            "priority": state.get("new_ticket_priority", "medium")
        }}]
    return []
