# Multi-Agent Customer Service System

A multi-agent customer service system using LangGraph for agent orchestration, MCP (Model Context Protocol) for tool access, and A2A (Agent-to-Agent) communication.

## Project Structure

```
main.py                      # End-to-end demo with test scenarios
orchestrator.py              # LangGraph workflow definition
agents/
 - router.py                # Router Agent (Orchestrator)
 - customer_data.py         # Customer Data Agent (MCP client)
 - support.py               # Support Agent (LLM-based)
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

### 2. Set OpenAI API Key While Running
```bash
export OPENAI_API_KEY="your-api-key"
```

### 3. Initalize the Database and Start MCP Server
```bash
cd mcp_server
python server.py
# Server runs on http://localhost:5001 as set, can be changed to other ports
```

### 5. Run Demo (in a new terminal)

```bash
python main.py
```

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
- **Flow**: Router → CustomerData (MCP) → Router → Support → END

### 2. Coordinated Query (Task Allocation)
- **Query**: "I'm customer 3 and need help upgrading my account"
- **Flow**: Router → CustomerData → Router (analyze tier) → Support → END

### 3. Complex Query
- **Query**: "Show me all active customers who have open tickets"
- **Flow**: Router → CustomerData (list) → Router → Support → END

### 4. Escalation
- **Query**: "I've been charged twice, please refund immediately!"
- **Flow**: Router (detect urgency) → Support (negotiation) → Router → CustomerData → Support → END

### 5. Multi-Intent
- **Query**: "I'm customer 2, update my email to new@email.com and show my ticket history"
- **Flow**: Router → CustomerData (update) → Router → CustomerData (history) → Router → Support → END

## A2A Communication

Agents communicate through shared state with explicit logging:
- `[Router → CustomerData]` - Data requests
- `[CustomerData → Router]` - Data responses (implicit via state)
- `[Router → Support]` - Support requests
- `[Support → Router]` - Negotiation or final response

