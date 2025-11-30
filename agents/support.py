import json
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI


SUPPORT_SYSTEM_PROMPT = """
You are a helpful customer support agent in a SaaS company.

You receive a structured "state" object that may contain:
- query: original user question
- customer_id: parsed customer id (if any)
- intents: list of intents detected by the router (billing, cancel, upgrade, report, history, update_email, etc.)
- urgency: high/None
- customer: a customer record (id, name, email, status, etc.) or null
- customers: list of customer records (for reporting)
- tickets: list of tickets for a single customer
- log: internal agent-to-agent log (do NOT expose directly)

Your job:
1. Use the available context to respond in natural language.
2. For urgent billing issues, acknowledge the urgency and mention that a high-priority ticket has been created (if state says so).
3. If there is clearly missing billing context (billing intent but no tickets and no history),
   you SHOULD NOT guess. Instead, ask the router to fetch billing info by setting:
   - state["needs"] = "billing_info"
   and return WITHOUT writing a user-facing response.
4. When a response is produced, write it to state["response"].
Reply in a concise, polite tone.
"""


_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def support_node(state: Dict[str, Any]) -> Dict[str, Any]:
    new_state = dict(state)
    log: List[str] = list(new_state.get("log", []))

    intents: List[str] = new_state.get("intents", [])
    tickets = new_state.get("tickets", [])
    urgency: Optional[str] = new_state.get("urgency")
    query: str = new_state.get("query", "")
    report_mode: Optional[str] = new_state.get("report_mode")
    customers = new_state.get("customers", [])
    tickets_by_customer = new_state.get("tickets_by_customer")
    asked_billing_once = new_state.get("asked_billing_info_once", False)


    # -------- Scenario 2: Negotiation / Escalation --------
    # billing intent but no history -> request billing_info from Router
    if "billing" in intents and not tickets and new_state.get("customer_id") is not None and not asked_billing_once:
        new_state["needs"] = "billing_info"
        new_state["next"] = "router"
        new_state["asked_billing_info_once"] = True
        log.append("[Support → Router] I need billing context (ticket history) before answering.")
        new_state["log"] = log
        return new_state

    # -------- Scenario 3: Multi-Step 报表 --------
    # Have premium customer list, but no high-priority tickets
    if report_mode == "premium_high_priority" and customers and tickets_by_customer is None:
        new_state["needs"] = "tickets_for_customers"
        new_state["next"] = "router"
        log.append("[Support → Router] Please fetch high-priority tickets for these premium customers.")
        new_state["log"] = log
        return new_state

    # Here means:
    # - billing scenario has tickets
    # - or report scenario has tickets_by_customer
    # - or normal support scenario, has enough context

    last_data = new_state.get("last_data_result", {})
    created_ticket = (
        isinstance(last_data, dict)
        and last_data.get("success")
        and "ticket" in last_data
    )

    # Construct simplified state for LLM
    state_for_llm = {
        "query": query,
        "customer_id": new_state.get("customer_id"),
        "intents": intents,
        "urgency": urgency,
        "customer": new_state.get("customer"),
        "customers": customers,
        "tickets": tickets,
        "tickets_by_customer": tickets_by_customer,
        "created_ticket": created_ticket,
        "report_mode": report_mode,
    }

    messages = [
        {"role": "system", "content": SUPPORT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "You are given a JSON state object. "
                "Use it to reply to the user in natural language. "
                "Here is the state:\n"
                f"{json.dumps(state_for_llm, indent=2)}"
            ),
        },
    ]

    result = _llm.invoke(messages)
    response_text = result.content.strip()

    new_state["response"] = response_text
    # Give control back to Router to return final result
    new_state["next"] = "router"
    log.append("[Support → Router] Final support response ready.")
    new_state["log"] = log
    return new_state
