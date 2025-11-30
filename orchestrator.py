# orchestrator.py
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from agents.router import router_node
from agents.customer_data import customer_data_node
from agents.support import support_node


class AgentState(TypedDict, total=False):
    """
    Shared state between Router / Customer Data / Support agents.
    Using TypedDict for proper LangGraph state management.
    """
    # Core
    query: str
    next: str  # "router" | "customer_data" | "support" | "end"
    
    # Router analysis
    customer_id: Optional[int]
    intents: List[str]
    urgency: Optional[str]
    initialized: bool
    report_mode: Optional[str]
    
    # Customer data
    customer: Optional[Dict[str, Any]]
    customers: List[Dict[str, Any]]
    tickets: List[Dict[str, Any]]
    tickets_by_customer: Optional[Dict[int, List[Dict[str, Any]]]]
    
    # Operations
    data_op: Optional[str]
    update_data: Dict[str, Any]
    new_ticket_issue: str
    new_ticket_priority: str
    needs: Optional[str]
    last_data_result: Dict[str, Any]
    
    # Control flags
    asked_support_once: bool
    asked_billing_info_once: bool
    email_updated: bool
    asked_history_once: bool
    step: int
    
    # Output
    response: str
    log: List[str]


def _route_from_router(state: Dict[str, Any]) -> str:
    """
    Router 之后去哪：
    - "customer_data" -> Customer Data Agent
    - "support"       -> Support Agent
    - 其他             -> END
    """
    nxt = state.get("next")
    if nxt == "customer_data":
        return "customer_data"
    if nxt == "support":
        return "support"
    # If Router itself has decided to end (e.g. already wrapped final response)
    return "end"


def _route_from_support(state: Dict[str, Any]) -> str:
    """
    After Support, if next == "router" return Router, otherwise end.
    """
    nxt = state.get("next")
    if nxt == "router":
        return "router"
    return "end"


def build_graph():
    """
    Build LangGraph multi-Agent flow:
    START → router → (customer_data / support) → ... → END
    """
    graph = StateGraph(AgentState)

    # Register three nodes
    graph.add_node("router", router_node)
    graph.add_node("customer_data", customer_data_node)
    graph.add_node("support", support_node)

    # Start: Router
    graph.add_edge(START, "router")

    # Router -> decide where to go based on state["next"]
    graph.add_conditional_edges(
        "router",
        _route_from_router,
        {
            "customer_data": "customer_data",
            "support": "support",
            "end": END,
        },
    )

    # After Customer Data runs, return to Router to decide next step
    graph.add_edge("customer_data", "router")

    # Support -> Router (sometimes need to negotiate again), or directly END
    graph.add_conditional_edges(
        "support",
        _route_from_support,
        {
            "router": "router",
            "end": END,
        },
    )

    return graph.compile()
