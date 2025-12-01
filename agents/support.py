"""
Support Agent - LLM-powered agent for customer support.
Implements A2A negotiation when needed, generates responses when data is sufficient.
"""
import json
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI


SUPPORT_SYSTEM_PROMPT = """You are a Support Agent in a multi-agent customer service system.

Based on the scenario and available data, either:
1. Generate a response if you have sufficient data
2. Request more data via "needs" if truly required

Scenarios:
- task_allocation: You have customer data → generate response directly
- negotiation: For billing/cancel issues, you may need billing_info (ticket history)
- multi_step: For reports, you may need tickets_for_customers

Output JSON:
{
    "action": "respond" | "negotiate",
    "needs": "billing_info" | "tickets_for_customers" | "active_customers" | null,
    "response": "your response to customer" | null,
    "a2a_message": "message to Router"
}

Rules:
- action="respond" → must have response, needs=null
- action="negotiate" → must have needs, response=null
- Only negotiate ONCE per type - if you already have the data, respond!
- If customer data exists, don't request customer_info again
- If tickets exist, don't request billing_info again
- If customers list exists, don't request active_customers again
"""

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def support_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Support Agent - handles responses and negotiations."""
    new_state = dict(state)
    log: List[str] = list(new_state.get("log", []))
    
    scenario = new_state.get("scenario", "task_allocation")
    has_customer = new_state.get("customer") is not None
    has_customers = len(new_state.get("customers", [])) > 0
    has_tickets = len(new_state.get("tickets", [])) > 0
    has_tickets_by_customer = new_state.get("tickets_by_customer") is not None
    
    # Track negotiations to prevent loops
    negotiation_done = new_state.get("support_negotiated", False)
    
    # Build context
    context = {
        "query": new_state.get("query", ""),
        "scenario": scenario,
        "customer_id": new_state.get("customer_id"),
        "intents": new_state.get("intents", []),
        "urgency": new_state.get("urgency"),
        "customer": new_state.get("customer"),
        "customers": new_state.get("customers", []),
        "tickets": new_state.get("tickets", []),
        "tickets_by_customer": new_state.get("tickets_by_customer"),
        "has_customer": has_customer,
        "has_customers": has_customers,
        "has_tickets": has_tickets,
        "has_tickets_by_customer": has_tickets_by_customer,
        "already_negotiated": negotiation_done,
    }

    messages = [
        {"role": "system", "content": SUPPORT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Handle request:\n{json.dumps(context, indent=2, default=str)}"}
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
        decision = {
            "action": "respond",
            "needs": None,
            "response": "I'll help you with your request. Please let me know if you need any specific assistance.",
            "a2a_message": "JSON parse error, generated fallback"
        }

    action = decision.get("action", "respond")
    needs = decision.get("needs")
    response = decision.get("response")
    a2a_msg = decision.get("a2a_message", "")

    # SAFETY: If negotiation requested but we already negotiated, force respond
    if action == "negotiate" and negotiation_done:
        log.append("[Support] Already negotiated once, forcing response")
        action = "respond"
        needs = None
        if not response:
            response = "Based on the available information, I'll assist you. Please let me know if you need more details."
    
    # SAFETY: If negotiation requested but data already exists, force respond
    if action == "negotiate" and needs:
        skip_negotiate = False
        if needs == "billing_info" and has_tickets:
            log.append("[Support] Tickets already exist, skipping billing_info request")
            skip_negotiate = True
        elif needs == "customer_info" and has_customer:
            log.append("[Support] Customer already exists, skipping customer_info request")
            skip_negotiate = True
        elif needs == "active_customers" and has_customers:
            log.append("[Support] Customers already exist, skipping active_customers request")
            skip_negotiate = True
        elif needs == "tickets_for_customers" and has_tickets_by_customer:
            log.append("[Support] Tickets by customer already exist, skipping request")
            skip_negotiate = True
        
        if skip_negotiate:
            action = "respond"
            needs = None
            if not response:
                response = "Based on the available information, I'll help you with your request."

    # Execute action
    if action == "negotiate" and needs:
        new_state["needs"] = needs
        new_state["support_negotiated"] = True
        new_state["next"] = "router"
        log.append(f"[Support → Router] Negotiation: Need {needs}")
        if a2a_msg:
            log.append(f"[Support → Router] {a2a_msg}")
    else:
        # Generate response
        if not response:
            response = "I'm here to help! Please let me know how I can assist you."
        new_state["response"] = response
        new_state["next"] = "router"
        log.append(f"[Support → Router] Response generated")
        if a2a_msg:
            log.append(f"[Support → Router] {a2a_msg}")

    new_state["log"] = log
    return new_state
