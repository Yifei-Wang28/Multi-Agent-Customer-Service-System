# Multi-Agent Customer Service System

A multi-agent customer service system using **LLM-powered AI Agents**, LangGraph for orchestration, MCP (Model Context Protocol) for tool access, and A2A (Agent-to-Agent) communication.

## Architecture Overview

All three agents are **LLM-powered** using GPT-4o-mini:

| Agent | Role | LLM Usage |
|-------|------|-----------|
| **Router Agent** | Orchestrator | Uses LLM to analyze queries, extract intents/entities, and make routing decisions |
| **Customer Data Agent** | Data Specialist | Uses LLM to decide which MCP tools to call and interpret results |
| **Support Agent** | Response Generator | Uses LLM to negotiate for data or generate customer responses |

## Project Structure

```
main.py                      # End-to-end demo with test scenarios
orchestrator.py              # LangGraph workflow definition
agents/
  - router.py                # Router Agent (LLM-powered orchestrator)
  - customer_data.py         # Customer Data Agent (LLM + MCP tools)
  - support.py               # Support Agent (LLM-powered responder)
mcp_server/
  - server.py                # MCP Server implementation
  - database_setup.py        # SQLite database setup
README.md
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install langchain langchain-openai langgraph requests
conda install -c conda-forge flask flask-cors
```

### 2. Set OpenAI API Key
```bash
export OPENAI_API_KEY="your-api-key"
```

### 3. Initialize Database and Start MCP Server
```bash
cd mcp_server
python server.py
# Server runs on http://localhost:5001
```

### 4. Run Demo (in a new terminal)
```bash
python main.py
```

## LLM-Powered Agents

### Router Agent (`agents/router.py`)
- **Input**: User query + current state
- **LLM Task**: Analyze query, extract customer_id, detect intents (billing, cancel, upgrade, etc.), determine urgency, decide next agent
- **Output**: JSON with routing decision
```json
{
    "customer_id": 5,
    "intents": ["get_info"],
    "urgency": null,
    "data_op": "get_customer",
    "next": "customer_data",
    "reasoning": "Need to fetch customer data first"
}
```

### Customer Data Agent (`agents/customer_data.py`)
- **Input**: Data operation request + state
- **LLM Task**: Decide which MCP tool(s) to call, construct arguments, interpret results
- **Output**: JSON with tool calls
```json
{
    "tool_calls": [{"tool": "get_customer", "args": {"customer_id": 5}}],
    "message_to_router": "Retrieved customer Charlie Brown"
}
```

### Support Agent (`agents/support.py`)
- **Input**: Customer query + available context
- **LLM Task**: Decide if more data needed (negotiate) or generate response
- **Output**: JSON with negotiation or response
```json
{
    "needs": null,
    "response": "Hello Charlie! How can I help you today?",
    "a2a_message": "Generated response with customer context"
}
```

## A2A Communication Protocol

Agents communicate through structured messages in shared state:

| Message Type | Example |
|--------------|---------|
| **Router → CustomerData** | `[Router] Decision: next=customer_data, data_op=get_customer` |
| **CustomerData → Router** | `[CustomerData → Router] Got customer: Charlie Brown` |
| **Router → Support** | `[Router] Decision: next=support, reasoning=Customer data available` |
| **Support → Router** | `[Support → Router] Need billing_info before responding` |
| **Support → Router** | `[Support → Router] Response generated` |

## MCP Server Tools

| Tool | Description |
|------|-------------|
| `get_customer(customer_id)` | Get customer by ID |
| `list_customers(status, limit)` | List customers with filters |
| `update_customer(customer_id, data)` | Update customer info |
| `create_ticket(customer_id, issue, priority)` | Create support ticket |
| `get_customer_history(customer_id)` | Get customer's tickets |

## Test Scenarios

### 1. Simple Query
- **Query**: "Get customer information for ID 5"
- **A2A Flow**: 
  1. Router (LLM analyzes) → CustomerData
  2. CustomerData (LLM calls MCP) → Router
  3. Router (LLM routes) → Support
  4. Support (LLM generates response) → END

### 2. Coordinated Query (Task Allocation)
- **Query**: "I'm customer 3 and need help upgrading my account"
- **A2A Flow**: Router extracts customer_id, fetches data, analyzes tier, routes to Support

### 3. Escalation with Negotiation
- **Query**: "I've been charged twice, please refund immediately!"
- **A2A Flow**: 
  1. Router detects urgency
  2. Support (LLM) → Router: "Need billing_info"
  3. Router → CustomerData → Router
  4. Support generates urgent response

### 4. Multi-Intent
- **Query**: "I'm customer 2, update my email to new@email.com and show my ticket history"
- **A2A Flow**: Router coordinates multiple data operations before Support response

## Conclusion

### What I Learned
Building LLM-powered agents taught me how to leverage language models for decision-making in multi-agent systems. Each agent uses its own system prompt to understand its role and output structured JSON for reliable A2A communication. The key insight is that LLMs excel at understanding natural language queries and making contextual decisions, while MCP provides a standardized way to expose tools.

### Challenges
The main challenge was ensuring reliable JSON parsing from LLM outputs and preventing infinite loops when agents negotiate. I implemented fallback mechanisms for parsing errors and tracking flags (like `asked_billing_info_once`) to prevent repeated negotiations. Another challenge was designing prompts that produce consistent, parseable outputs while allowing flexibility in handling diverse queries.
