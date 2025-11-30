# main.py
from typing import List, Dict, Any

from orchestrator import build_graph


def pretty_print_scenario_result(name: str, query: str, result: Dict[str, Any]):
    print("\n" + "=" * 80)
    print(f"SCENARIO: {name}")
    print("-" * 80)
    print(f"Query:\n  {query}\n")
    print("Response:")
    print(result.get("response", "(no response generated)"))

    print("\nAgent Communication Log:")
    log: List[str] = result.get("log", [])
    if not log:
        print("  (no log)")
        return

    for line in log:
        print("  " + line)


def main():
    """
    End-to-end demo for all assignment test scenarios.

    NOTE:
    - Make sure the MCP server is running before calling this:
        cd mcp_server
        python server.py
    """
    agent = build_graph()

    scenarios = [
        # 1) Simple Query: Single agent, direct MCP
        {
            "name": "Simple Query",
            "query": "Get customer information for ID 5",
        },
        # 2) Coordinated Query: Router + Data + Support
        {
            "name": "Coordinated Query",
            "query": "I'm customer 3 and need help upgrading my account",
        },
        # 3) Complex Query: Requires negotiation between data and support
        {
            "name": "Complex Query",
            "query": "Show me all active customers who have open tickets",
        },
        # 4) Escalation: Urgent billing issue
        {
            "name": "Escalation",
            "query": "I've been charged twice, please refund immediately!",
        },
        # 5) Multi-Intent: update email + show ticket history
        {
            "name": "Multi-Intent",
            "query": "I'm customer 2, update my email to new@email.com and show my ticket history",
        },
    ]

    for s in scenarios:
        result = agent.invoke({"query": s["query"]})
        pretty_print_scenario_result(s["name"], s["query"], result)


if __name__ == "__main__":
    main()
