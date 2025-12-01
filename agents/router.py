"""
Router Agent - LLM-powered orchestrator for multi-agent coordination.
Implements the three A2A scenarios: Task Allocation, Negotiation, Multi-Step.
"""
import json
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI


ROUTER_SYSTEM_PROMPT = """You are a Router Agent orchestrating a customer service system.

Analyze the query and current state, then output a JSON decision.

Your job:
1. First time: Extract customer_id, detect intents, determine scenario type
2. Subsequent calls: Route based on what data is available and what's needed

Scenario types:
- "task_allocation": Simple query with customer ID → get data → support responds
- "negotiation": Multiple intents (cancel+billing, etc.) → may need Support to request more data
- "multi_step": Report queries about multiple customers → get customers → get their tickets

Output JSON:
{
    "customer_id": <int or null>,
    "intents": ["billing", "cancel", "upgrade", "report", "history", "get_info"],
    "urgency": "high" | null,
    "scenario": "task_allocation" | "negotiation" | "multi_step",
    "data_op": "get_customer" | "get_customer_history" | "list_active_customers" | "get_high_priority_for_customers" | "update_customer" | null,
    "update_data": {"email": "..."} | null,
    "next": "customer_data" | "support" | "end",
    "reasoning": "brief explanation"
}

Rules:
- If "response" exists → next="end"
- If "needs" is set by Support → fulfill it via customer_data
- For task_allocation: get customer first, then support
- For negotiation: go to support first, it may request billing_info
- For multi_step: get customers list first, then support coordinates
"""

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Router Agent - orchestrates the multi-agent flow."""
    new_state = dict(state)
    log: List[str] = list(new_state.get("log", []))

    step = new_state.get("step", 0) + 1
    new_state["step"] = step
    
    # Safety: max steps
    if step > 15:
        log.append("[Router] Step limit reached, ending.")
        new_state["log"] = log
        new_state["next"] = "end"
        return new_state

    # RULE 1: If response exists, we're done
    if new_state.get("response"):
        log.append("[Router] Response received. Returning to user.")
        new_state["log"] = log
        new_state["next"] = "end"
        return new_state

    # RULE 2: If Support requested data (needs), fulfill it
    needs = new_state.get("needs")
    if needs:
        new_state["needs"] = None
        if needs == "billing_info":
            new_state["data_op"] = "get_customer_history"
            log.append(f"[Router → CustomerData] Support needs billing info, fetching ticket history")
        elif needs == "tickets_for_customers":
            new_state["data_op"] = "get_high_priority_for_customers"
            log.append(f"[Router → CustomerData] Support needs tickets for customers")
        elif needs == "customer_info":
            new_state["data_op"] = "get_customer"
            log.append(f"[Router → CustomerData] Support needs customer info")
        elif needs == "active_customers":
            new_state["data_op"] = "list_active_customers"
            log.append(f"[Router → CustomerData] Support needs active customers list")
        new_state["next"] = "customer_data"
        new_state["log"] = log
        return new_state

    # Build context for LLM
    context = {
        "query": new_state.get("query", ""),
        "customer_id": new_state.get("customer_id"),
        "intents": new_state.get("intents"),
        "scenario": new_state.get("scenario"),
        "customer": new_state.get("customer"),
        "customers": new_state.get("customers", []),
        "tickets": new_state.get("tickets", []),
        "tickets_by_customer": new_state.get("tickets_by_customer"),
        "response": new_state.get("response"),
    }

    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": f"State:\n{json.dumps(context, indent=2, default=str)}"}
    ]

    result = _llm.invoke(messages)
    response_text = result.content.strip()
    
    # Parse JSON
    try:
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        decision = json.loads(response_text.strip())
    except json.JSONDecodeError:
        log.append("[Router] JSON parse error, routing to support")
        new_state["next"] = "support"
        new_state["log"] = log
        return new_state

    # Apply decision
    if not new_state.get("initialized"):
        new_state["customer_id"] = decision.get("customer_id")
        new_state["intents"] = decision.get("intents", [])
        new_state["urgency"] = decision.get("urgency")
        new_state["scenario"] = decision.get("scenario", "task_allocation")
        new_state["initialized"] = True

    if decision.get("update_data"):
        new_state["update_data"] = decision["update_data"]

    if decision.get("data_op"):
        new_state["data_op"] = decision["data_op"]

    next_agent = decision.get("next", "support")
    
    # Safety: can't end without response
    if next_agent == "end" and not new_state.get("response"):
        next_agent = "support"
    
    new_state["next"] = next_agent
    
    reasoning = decision.get("reasoning", "")
    log.append(f"[Router] Decision: next={next_agent}, scenario={new_state.get('scenario')}, data_op={decision.get('data_op')}")
    if reasoning:
        log.append(f"[Router] {reasoning}")

    new_state["log"] = log
    return new_state
