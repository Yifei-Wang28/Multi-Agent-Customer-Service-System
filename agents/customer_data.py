import json
from typing import Any, Dict, List, Optional

import requests


MCP_URL = "http://localhost:5001/mcp"


def _call_mcp_tool(name: str, arguments: Dict[str, Any], message_id: int = 1) -> Dict[str, Any]:
    message = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments or {},
        },
    }

    resp = requests.post(
        MCP_URL,
        json=message,
        headers={"Content-Type": "application/json"},
        stream=True,
        timeout=10,
    )

    # SSE: each line starts with "data: "
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
            return {
                "success": False,
                "error": f"MCP error: {payload['error']}",
            }

    return {
        "success": False,
        "error": "Empty or invalid MCP response",
    }


def customer_data_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Customer Data Agent node.
    According to state["data_op"] decide which MCP tool to call,
    then write the result back to state (customer / customers / tickets etc.).
    After completion, return control to Router: state["next"] = "router"
    """
    data_op: Optional[str] = state.get("data_op")
    if not data_op:
        # No data operation to do, directly return to Router
        new_state = dict(state)
        new_state["next"] = "router"
        return new_state

    customer_id: Optional[int] = state.get("customer_id")
    update_data: Dict[str, Any] = state.get("update_data", {}) or {}
    new_state = dict(state)
    log: List[str] = list(new_state.get("log", []))

    # Call different MCP tools
    if data_op == "get_customer" and customer_id is not None:
        result = _call_mcp_tool("get_customer", {"customer_id": customer_id})
        if result.get("success"):
            new_state["customer"] = result.get("customer")
        new_state["last_data_result"] = result
        log.append(f"[Data] get_customer({customer_id}) -> success={result.get('success')}")

    elif data_op == "get_customer_history" and customer_id is not None:
        result = _call_mcp_tool("get_customer_history", {"customer_id": customer_id})
        if result.get("success"):
            new_state["tickets"] = result.get("tickets", [])
        new_state["last_data_result"] = result
        log.append(f"[Data] get_customer_history({customer_id}) -> success={result.get('success')}")

    elif data_op == "list_active_customers":
        result = _call_mcp_tool("list_customers", {"status": "active"})
        if result.get("success"):
            new_state["customers"] = result.get("customers", [])
        new_state["last_data_result"] = result
        log.append("[Data] list_customers(status='active')")

    elif data_op == "update_customer" and customer_id is not None and update_data:
        result = _call_mcp_tool(
            "update_customer",
            {"customer_id": customer_id, "data": update_data},
        )
        if result.get("success"):
            new_state["customer"] = result.get("customer")
        new_state["last_data_result"] = result
        log.append(f"[Data] update_customer({customer_id}, {update_data}) -> success={result.get('success')}")

    elif data_op == "create_ticket" and customer_id is not None:
        issue: str = new_state.get("new_ticket_issue", "")
        priority: str = new_state.get("new_ticket_priority", "medium")
        result = _call_mcp_tool(
            "create_ticket",
            {
                "customer_id": customer_id,
                "issue": issue,
                "priority": priority,
            },
        )
        if result.get("success"):
            # Add new ticket to tickets list
            tickets = list(new_state.get("tickets", []))
            if "ticket" in result:
                tickets.append(result["ticket"])
            new_state["tickets"] = tickets
        new_state["last_data_result"] = result
        log.append(
            f"[Data] create_ticket({customer_id}, priority={priority}) -> success={result.get('success')}"
        )
    elif data_op == "get_high_priority_for_customers":
        customers = new_state.get("customers", [])
        tickets_by_customer = {}
        for c in customers:
            cid = c.get("id")
            if cid is None:
                continue
            result = _call_mcp_tool("get_customer_history", {"customer_id": cid})
            if not result.get("success"):
                continue
            all_tickets = result.get("tickets", [])
            high_tickets = [t for t in all_tickets if t.get("priority") == "high"]
            if high_tickets:
                tickets_by_customer[cid] = high_tickets

        new_state["tickets_by_customer"] = tickets_by_customer
        new_state["last_data_result"] = {"success": True, "count": len(tickets_by_customer)}
        log.append(
            f"[CustomerData → Router] Collected high-priority tickets for "
            f"{len(tickets_by_customer)} premium customers"
        )


    # Clear data_op, return to Router
    new_state["data_op"] = None
    new_state["next"] = "router"
    new_state["log"] = log
    return new_state
