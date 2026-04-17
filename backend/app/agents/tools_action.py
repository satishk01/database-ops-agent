"""Action tools for safe database operations."""

import re
import json
from strands import tool
from app.db import execute_command, execute_query

# Dangerous SQL patterns that must be blocked
BLOCKED_PATTERNS = [
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX(?!\s+CONCURRENTLY))\b",
    r"\bDELETE\s+FROM\b",
    r"\bTRUNCATE\b",
    r"\bALTER\s+TABLE\s+\w+\s+DROP\b",
    r"\bUPDATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
]


def _is_safe_sql(sql: str) -> tuple[bool, str]:
    """Validate SQL against blocked patterns."""
    upper = sql.upper().strip()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, upper):
            return False, f"Blocked: matches dangerous pattern '{pattern}'"
    return True, "OK"


@tool
def create_index_concurrently(table_name: str, column_names: str, index_name: str) -> str:
    """
    Create an index CONCURRENTLY on a table without blocking reads/writes.

    Args:
        table_name: The table to create the index on.
        column_names: Comma-separated column names for the index.
        index_name: Name for the new index.
    """
    # Sanitize inputs
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        return json.dumps({"error": "Invalid table name"})
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_, ]*$", column_names):
        return json.dumps({"error": "Invalid column names"})
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", index_name):
        return json.dumps({"error": "Invalid index name"})

    sql = f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} ON {table_name} ({column_names})"
    safe, reason = _is_safe_sql(sql)
    if not safe:
        return json.dumps({"error": reason})

    result = execute_command(sql)
    return json.dumps({"action": "create_index_concurrently", "sql": sql, "result": result})


@tool
def analyze_table(table_name: str) -> str:
    """
    Run ANALYZE on a table to update planner statistics.

    Args:
        table_name: The table to analyze.
    """
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", table_name):
        return json.dumps({"error": "Invalid table name"})

    sql = f"ANALYZE {table_name}"
    result = execute_command(sql)
    return json.dumps({"action": "analyze_table", "table": table_name, "result": result})


@tool
def vacuum_table(table_name: str) -> str:
    """
    Run VACUUM (non-full) on a table to reclaim dead tuple space without locking.

    Args:
        table_name: The table to vacuum.
    """
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", table_name):
        return json.dumps({"error": "Invalid table name"})

    sql = f"VACUUM {table_name}"
    result = execute_command(sql)
    return json.dumps({"action": "vacuum_table", "table": table_name, "result": result})
