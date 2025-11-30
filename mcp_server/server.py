import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Any

from flask import Flask, request, Response, jsonify
from flask_cors import CORS

from database_setup import DatabaseSetup

# -------------------------------------------------------------------
# Database init 
# -------------------------------------------------------------------

DB_PATH = Path(__file__).with_name("support.db")


def init_database() -> None:
    """
    Initialize the SQLite database using DatabaseSetup.
    - Create tables & triggers if needed
    - Insert sample data once when the database is empty
    """
    db = DatabaseSetup(str(DB_PATH))
    db.connect()
    db.create_tables()
    db.create_triggers()

    # Only insert sample data if there are no customers yet
    db.cursor.execute("SELECT COUNT(*) FROM customers")
    count = db.cursor.fetchone()[0]
    if count == 0:
        db.insert_sample_data()

    db.close()


def get_db_connection() -> sqlite3.Connection:
    """
    Create a database connection with foreign keys and row_factory.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a SQLite row to a plain dictionary."""
    return {key: row[key] for key in row.keys()}


# -------------------------------------------------------------------
# Tool implementations (assignment-required tools)
# -------------------------------------------------------------------

def tool_get_customer(customer_id: int) -> Dict[str, Any]:
    """
    Retrieve a specific customer by ID.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return {"success": False, "error": f"Customer with ID {customer_id} not found"}

        return {"success": True, "customer": row_to_dict(row)}
    except Exception as e:
        return {"success": False, "error": f"Database error: {e}"}


def tool_list_customers(
    status: Optional[str] = None, limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    List customers, optionally filtered by status and limited in count.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        params: List[Any] = []
        query = "SELECT * FROM customers"

        if status:
            if status not in ("active", "disabled"):
                return {
                    "success": False,
                    "error": 'Invalid status. Must be "active" or "disabled".',
                }
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        if limit is not None:
            safe_limit = max(1, min(int(limit), 500))
            query += f" LIMIT {safe_limit}"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        customers = [row_to_dict(r) for r in rows]
        return {"success": True, "count": len(customers), "customers": customers}
    except Exception as e:
        return {"success": False, "error": f"Database error: {e}"}


def tool_update_customer(customer_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update customer fields. `data` is a dict of fields -> new values.
    Allowed fields: name, email, phone, status.
    """
    allowed_fields = {"name", "email", "phone", "status"}

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure customer exists
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        existing = cursor.fetchone()
        if existing is None:
            conn.close()
            return {"success": False, "error": f"Customer with ID {customer_id} not found"}

        if not isinstance(data, dict) or not data:
            conn.close()
            return {"success": False, "error": "Update data must be a non-empty object"}

        updates: List[str] = []
        params: List[Any] = []

        for key, value in data.items():
            if key not in allowed_fields:
                # Ignore unknown fields instead of failing hard
                continue
            if key == "status" and value not in ("active", "disabled"):
                conn.close()
                return {
                    "success": False,
                    "error": 'Invalid status. Must be "active" or "disabled".',
                }
            updates.append(f"{key} = ?")
            params.append(value)

        if not updates:
            conn.close()
            return {
                "success": False,
                "error": "No valid fields to update. Allowed: name, email, phone, status.",
            }

        # updated_at is handled by your trigger, no need to set manually
        params.append(customer_id)
        query = f"UPDATE customers SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        updated = cursor.fetchone()
        conn.close()

        return {
            "success": True,
            "message": f"Customer {customer_id} updated successfully",
            "customer": row_to_dict(updated),
        }
    except Exception as e:
        return {"success": False, "error": f"Database error: {e}"}


def tool_create_ticket(customer_id: int, issue: str, priority: str) -> Dict[str, Any]:
    """
    Create a new support ticket for a customer.
    """
    priority = priority.lower()
    if priority not in ("low", "medium", "high"):
        return {
            "success": False,
            "error": 'Invalid priority. Must be "low", "medium", or "high".',
        }

    if not issue or not issue.strip():
        return {"success": False, "error": "Issue description is required."}

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure customer exists
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        customer = cursor.fetchone()
        if customer is None:
            conn.close()
            return {"success": False, "error": f"Customer with ID {customer_id} not found"}

        cursor.execute(
            """
            INSERT INTO tickets (customer_id, issue, status, priority)
            VALUES (?, ?, 'open', ?)
            """,
            (customer_id, issue.strip(), priority),
        )
        ticket_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cursor.fetchone()
        conn.close()

        return {
            "success": True,
            "message": f"Ticket {ticket_id} created successfully",
            "ticket": row_to_dict(ticket),
        }
    except Exception as e:
        return {"success": False, "error": f"Database error: {e}"}


def tool_get_customer_history(customer_id: int) -> Dict[str, Any]:
    """
    Return all tickets associated with a given customer_id.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure customer exists
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        customer = cursor.fetchone()
        if customer is None:
            conn.close()
            return {"success": False, "error": f"Customer with ID {customer_id} not found"}

        cursor.execute(
            """
            SELECT * FROM tickets
            WHERE customer_id = ?
            ORDER BY created_at DESC
            """,
            (customer_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        tickets = [row_to_dict(r) for r in rows]
        return {
            "success": True,
            "customer_id": customer_id,
            "count": len(tickets),
            "tickets": tickets,
        }
    except Exception as e:
        return {"success": False, "error": f"Database error: {e}"}


# -------------------------------------------------------------------
# MCP server (Flask + SSE)
# -------------------------------------------------------------------

app = Flask(__name__)
CORS(app)

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_customer",
        "description": "Retrieve a specific customer by their ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "The unique ID of the customer to retrieve",
                }
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "list_customers",
        "description": "List customers, optionally filtered by status and limited in count.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "disabled"],
                    "description": "Optional filter by customer status",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of customers to return",
                },
            },
        },
    },
    {
        "name": "update_customer",
        "description": "Update a customer's fields. Allowed fields: name, email, phone, status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "The unique ID of the customer to update",
                },
                "data": {
                    "type": "object",
                    "description": "Fields to update (name, email, phone, status)",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "phone": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["active", "disabled"],
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["customer_id", "data"],
        },
    },
    {
        "name": "create_ticket",
        "description": "Create a new support ticket for a customer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "The customer ID this ticket belongs to",
                },
                "issue": {
                    "type": "string",
                    "description": "Description of the customer's issue",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Ticket priority",
                },
            },
            "required": ["customer_id", "issue", "priority"],
        },
    },
    {
        "name": "get_customer_history",
        "description": "Get all tickets for a given customer ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "The unique ID of the customer",
                }
            },
            "required": ["customer_id"],
        },
    },
]


def create_sse_message(data: Dict[str, Any]) -> str:
    """Format a dict as a single Server-Sent Event."""
    return f"data: {json.dumps(data)}\n\n"


def handle_initialize(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle MCP initialize request.
    """
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "customer-support-mcp-server",
                "version": "1.0.0",
            },
        },
    }


def handle_tools_list(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle tools/list request.
    """
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {"tools": MCP_TOOLS},
    }


def handle_tools_call(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle tools/call request by dispatching to the appropriate function.
    """
    params = message.get("params") or {}
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}

    tool_functions = {
        "get_customer": tool_get_customer,
        "list_customers": tool_list_customers,
        "update_customer": tool_update_customer,
        "create_ticket": tool_create_ticket,
        "get_customer_history": tool_get_customer_history,
    }

    if tool_name not in tool_functions:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
        }

    try:
        result = tool_functions[tool_name](**arguments)
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result),
                    }
                ]
            },
        }
    except TypeError as e:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32602, "message": f"Invalid params: {e}"},
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32603, "message": f"Tool execution error: {e}"},
        }


def process_mcp_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route MCP message to the appropriate handler.
    """
    method = message.get("method")

    if method == "initialize":
        return handle_initialize(message)
    if method == "tools/list":
        return handle_tools_list(message)
    if method == "tools/call":
        return handle_tools_call(message)

    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


@app.route("/mcp", methods=["POST"])
def mcp_endpoint() -> Response:
    """
    Main MCP endpoint.
    Accepts a JSON RPC request and streams a single SSE response.
    """
    message = request.get_json(force=True, silent=True)
    if message is None:
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Invalid JSON in request body"},
        }
        return Response(create_sse_message(error_response), mimetype="text/event-stream")

    def generate():
        response = process_mcp_message(message)
        yield create_sse_message(response)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/health", methods=["GET"])
def health_check():
    """
    Simple health check.
    """
    return jsonify(
        {
            "status": "healthy",
            "server": "customer-support-mcp-server",
            "version": "1.0.0",
        }
    )


# Initialize DB when module is imported
init_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
