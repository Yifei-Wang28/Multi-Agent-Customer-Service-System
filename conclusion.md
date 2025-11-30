# Conclusion

## What I Learned

Building this multi-agent system taught me the importance of proper state management in agent orchestration. LangGraph's `TypedDict`-based state allows clean coordination between agents, while MCP provides a standardized way to expose database tools. The A2A communication pattern—where agents pass messages through shared state rather than direct calls—enables flexible routing and negotiation flows.

## Challenges

The main challenge I faced when I was testing was preventing infinite loops in the agent graph. When Support returns to Router, Router must correctly identify whether to continue processing or end the conversation. I solved this by implementing a "response check" at the beginning of the Router node—if a response already exists, immediately end. Another challenge was designing a general routing logic that works for all scenarios without overfitting to specific queries. The solution was to use a phased approach: first handle negotiation requests, then ensure customer data is fetched (general rule), then apply scenario-specific logic.