import re
from typing import Any, Dict, List, Optional


def _extract_customer_id(text: str) -> Optional[int]:
    """
    Simple extraction of customer ID from text:
    Match 'customer id 12345', 'id 5', 'customer 12345' etc.
    """
    lower = text.lower()
    # First find "customer id 12345" or "customer 12345"
    m = re.search(r"customer(?:\s+id)?\s+(\d+)", lower)
    if m:
        return int(m.group(1))
    # Then find "id 12345"
    m = re.search(r"\bid\s+(\d+)", lower)
    if m:
        return int(m.group(1))
    return None


def _extract_email(text: str) -> Optional[str]:
    """Extract the first email from text, consider it as a new email."""
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if m:
        return m.group(0)
    return None


def _detect_intents(query: str) -> List[str]:
    """
    Simple intent recognition (non-LLM version):
    - cancel, billing, upgrade, report, history, update_email, get_info
    """
    s = query.lower()
    intents: List[str] = []

    if "cancel" in s or "terminate" in s:
        intents.append("cancel")
    if "billing" in s or "charged" in s or "invoice" in s or "refund" in s:
        intents.append("billing")
    if "upgrade" in s or "premium" in s:
        intents.append("upgrade")
    if "status" in s or "high-priority" in s or "high priority" in s or "all active customers" in s:
        intents.append("report")
    if "history" in s or "ticket history" in s:
        intents.append("history")
    if "update my email" in s or "change my email" in s or "update email" in s:
        intents.append("update_email")
    # General info request
    if "get" in s or "show" in s or "information" in s or "info" in s or "help" in s:
        intents.append("get_info")

    return list(dict.fromkeys(intents))  # Remove duplicates, preserve order


def _detect_urgency(query: str) -> Optional[str]:
    s = query.lower()
    if "immediately" in s or "asap" in s or "charged twice" in s or "urgent" in s:
        return "high"
    return None


def router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Router Agent - Orchestrates the multi-agent flow.
    
    Design principles:
    1. If response exists -> END (final response ready)
    2. Handle Support's negotiation requests (needs)
    3. GENERAL RULE: If customer_id exists but no customer data -> fetch it first
    4. Then route to appropriate handler based on intents/scenario
    """
    new_state = dict(state)
    log: List[str] = list(new_state.get("log", []))

    step = new_state.get("step", 0) + 1
    new_state["step"] = step
    if step > 20:
        log.append("[Router] Step limit (20) reached, ending conversation.")
        new_state["log"] = log
        new_state["next"] = "end"
        return new_state

    # ========== PHASE 0: Check if we're done ==========
    if new_state.get("response"):
        log.append("[Router] Support response received. Returning final response to user.")
        new_state["log"] = log
        new_state["next"] = "end"
        return new_state

    query: str = new_state.get("query", "")

    # ========== PHASE 1: Initialize (first time only) ==========
    if not new_state.get("initialized"):
        customer_id = _extract_customer_id(query)
        intents = _detect_intents(query)
        urgency = _detect_urgency(query)

        new_state["customer_id"] = new_state.get("customer_id") or customer_id
        new_state["intents"] = intents
        new_state["urgency"] = urgency
        new_state["initialized"] = True

        # Detect special modes
        q_lower = query.lower()
        if "high-priority tickets" in q_lower or "high priority tickets" in q_lower:
            if "premium customers" in q_lower:
                new_state["report_mode"] = "premium_high_priority"

        if "update_email" in intents:
            new_email = _extract_email(query)
            if new_email:
                new_state["update_data"] = {"email": new_email}

        log.append(
            f"[Router] initialized | customer_id={new_state.get('customer_id')} "
            f"| intents={new_state.get('intents')} | urgency={new_state.get('urgency')} "
            f"| report_mode={new_state.get('report_mode')}"
        )

    # Extract commonly used state values
    intents: List[str] = new_state.get("intents", [])
    customer_id: Optional[int] = new_state.get("customer_id")
    needs: Optional[str] = new_state.get("needs")
    report_mode: Optional[str] = new_state.get("report_mode")
    customer = new_state.get("customer")
    customers = new_state.get("customers", [])
    tickets = new_state.get("tickets", [])
    tickets_by_customer = new_state.get("tickets_by_customer")

    # ========== PHASE 2: Handle Support's negotiation requests ==========
    # Support requested billing info
    if needs == "billing_info" and customer_id is not None:
        new_state["data_op"] = "get_customer_history"
        new_state["needs"] = None
        new_state["next"] = "customer_data"
        log.append(f"[Router → CustomerData] Get billing history for customer {customer_id} (Support negotiation)")
        new_state["log"] = log
        return new_state

    # Support requested tickets for multiple customers
    if needs == "tickets_for_customers" and customers:
        new_state["data_op"] = "get_high_priority_for_customers"
        new_state["needs"] = None
        new_state["next"] = "customer_data"
        log.append("[Router → CustomerData] Get high-priority tickets for customers (Support negotiation)")
        new_state["log"] = log
        return new_state

    # ========== PHASE 3: GENERAL RULE - Ensure customer data is fetched ==========
    # If we have a customer_id but no customer data yet, fetch it first
    # This applies to ALL scenarios that need customer context
    if customer_id is not None and customer is None and report_mode != "premium_high_priority":
        new_state["data_op"] = "get_customer"
        new_state["next"] = "customer_data"
        log.append(f"[Router → CustomerData] Get customer info for ID {customer_id}")
        new_state["log"] = log
        return new_state

    # ========== PHASE 4: Scenario-specific routing ==========
    
    # --- Scenario 3: Multi-Step Coordination (premium high-priority report) ---
    if report_mode == "premium_high_priority":
        # Step 1: Get all premium customers
        if not customers:
            new_state["data_op"] = "list_active_customers"
            new_state["next"] = "customer_data"
            log.append("[Router → CustomerData] Get all premium (active) customers")
            new_state["log"] = log
            return new_state

        # Step 2: Ask Support to request tickets (triggers negotiation)
        if tickets_by_customer is None and needs is None:
            new_state["next"] = "support"
            log.append("[Router → Support] We have premium customers. Request high-priority tickets.")
            new_state["log"] = log
            return new_state

        # Step 3: All data ready, format report
        if tickets_by_customer is not None:
            new_state["next"] = "support"
            log.append("[Router → Support] All data ready. Format the final report.")
            new_state["log"] = log
            return new_state

    # --- Scenario 2: Negotiation/Escalation (cancel + billing) ---
    if "cancel" in intents and "billing" in intents:
        # First ask Support if it can handle
        if not new_state.get("asked_support_once"):
            new_state["asked_support_once"] = True
            log.append("[Router → Support] Can you handle cancellation + billing together?")
            new_state["next"] = "support"
            new_state["log"] = log
            return new_state
        # After negotiation, Support has context now
        log.append("[Router → Support] Context gathered. Draft coordinated response.")
        new_state["next"] = "support"
        new_state["log"] = log
        return new_state

    # --- Multi-intent: Update email + ticket history ---
    if "update_email" in intents and customer_id is not None:
        # Step 1: Update email
        if new_state.get("update_data") and not new_state.get("email_updated"):
            new_state["data_op"] = "update_customer"
            new_state["email_updated"] = True
            new_state["next"] = "customer_data"
            log.append(f"[Router → CustomerData] Update email for customer {customer_id}")
            new_state["log"] = log
            return new_state

        # Step 2: Get ticket history
        if "history" in intents and not tickets and not new_state.get("asked_history_once"):
            new_state["data_op"] = "get_customer_history"
            new_state["asked_history_once"] = True
            new_state["next"] = "customer_data"
            log.append(f"[Router → CustomerData] Get ticket history for customer {customer_id}")
            new_state["log"] = log
            return new_state

        # All done, let Support summarize
        log.append("[Router → Support] Data operations complete. Summarize for user.")
        new_state["next"] = "support"
        new_state["log"] = log
        return new_state

    # --- Scenario 1 & General: Customer has data, route to Support ---
    if customer is not None:
        # Analyze customer tier (for Scenario 1 logging)
        tier = "premium" if customer.get("status") == "active" else customer.get("status")
        log.append(f"[Router] Analyzed customer tier: {tier}")
        log.append(f"[Router → Support] Handle request for {tier} customer (ID {customer_id})")
        new_state["next"] = "support"
        new_state["log"] = log
        return new_state

    # ========== PHASE 5: Default fallback ==========
    # No customer_id, no specific scenario - generic support
    new_state["next"] = "support"
    log.append("[Router → Support] Handle generic support request.")
    new_state["log"] = log
    return new_state
