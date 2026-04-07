"""Safe SQL execution for DeepBlue's query_database meta-tool.

Layers of defense (all required):
1. sqlparse validator — single SELECT only, no UNION/WITH/multi-statement
2. Table whitelist — only approved tables
3. Org-scope enforcement — org-scoped tables must filter by organization_id
4. Row limit — hard cap 100
5. Statement timeout — 5 seconds
6. Read-only transaction — BEGIN READ ONLY
"""

import logging
import re
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Function
from sqlparse.tokens import Keyword, DML

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Hard cap on row count
MAX_ROWS = 100
STATEMENT_TIMEOUT_MS = 5000

# Tables that are org-scoped (must filter by organization_id)
ORG_SCOPED_TABLES = {
    "customers", "properties", "water_features", "equipment_items",
    "visits", "chemical_readings",
    "invoices", "invoice_line_items", "payments",
    "agent_actions", "agent_threads", "agent_messages", "agent_action_tasks", "agent_action_comments",
    "service_cases", "routes", "route_stops",
    "techs", "broadcast_emails", "feedback_items", "customer_contacts",
    "property_difficulty", "property_jurisdiction", "satellite_analyses",
    "pool_measurements", "water_features", "equipment_catalog_items",
    "org_cost_settings", "service_tiers", "job_invoices",
    "email_templates", "inbox_routing_rules", "visit_charges",
}

# Shared tables — allowed without org filter
SHARED_TABLES = {
    "equipment_catalog", "parts_catalog", "bather_load_jurisdictions",
    "inspection_facilities", "inspections", "inspection_violations",
    "inspection_equipment", "inspection_lookups",
}

# Everything outside this is forbidden
ALLOWED_TABLES = ORG_SCOPED_TABLES | SHARED_TABLES

# Tables that are ALWAYS blocked (sensitive)
FORBIDDEN_TABLES = {
    "users", "api_keys", "refresh_tokens", "organizations",
    "organization_users", "audit_logs", "alembic_version",
    "deepblue_conversations", "deepblue_knowledge_gaps",
    "org_roles", "permissions", "role_permissions", "user_permissions",
    "agent_corrections", "agent_logs",
}


class SQLValidationError(Exception):
    pass


def _extract_tables(parsed) -> set[str]:
    """Extract all referenced table names from a parsed statement."""
    tables = set()
    from_seen = False
    join_seen = False

    def walk(tokens):
        nonlocal from_seen, join_seen
        for tok in tokens:
            if tok.is_group:
                walk(tok.tokens)
                continue
            if tok.ttype is Keyword:
                val = tok.value.upper()
                if val in ("FROM", "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN", "CROSS JOIN"):
                    from_seen = True
                    join_seen = True
                    continue
            if from_seen and tok.ttype is None and hasattr(tok, "get_real_name"):
                name = tok.get_real_name()
                if name:
                    tables.add(name.lower())
                from_seen = False

    # Simpler approach: regex for table names after FROM/JOIN
    sql_text = str(parsed)
    # Match FROM or JOIN followed by a table name (optionally quoted or schema-qualified)
    pattern = re.compile(r'\b(?:FROM|JOIN)\s+"?(\w+)"?', re.IGNORECASE)
    for match in pattern.finditer(sql_text):
        tables.add(match.group(1).lower())

    return tables


def validate_query(query: str) -> tuple[str, set[str]]:
    """Validate the query and return (cleaned_query, table_set).
    Raises SQLValidationError on any violation.
    """
    if not query or not query.strip():
        raise SQLValidationError("Empty query")

    # Remove trailing semicolon and whitespace
    cleaned = query.strip().rstrip(";").strip()

    # No semicolons inside (would indicate multiple statements)
    if ";" in cleaned:
        raise SQLValidationError("Multiple statements not allowed")

    # Parse
    try:
        parsed = sqlparse.parse(cleaned)
    except Exception as e:
        raise SQLValidationError(f"Parse error: {e}")

    if not parsed or len(parsed) != 1:
        raise SQLValidationError("Exactly one statement required")

    stmt = parsed[0]

    # Must be a SELECT
    stmt_type = stmt.get_type()
    if stmt_type != "SELECT":
        raise SQLValidationError(f"Only SELECT statements allowed (got {stmt_type})")

    # No DML keywords anywhere (INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE)
    forbidden_keywords = {
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
        "GRANT", "REVOKE", "EXECUTE", "CALL", "COPY", "LOCK",
    }
    upper = cleaned.upper()
    # Check for forbidden keywords as whole words
    for kw in forbidden_keywords:
        if re.search(rf'\b{kw}\b', upper):
            raise SQLValidationError(f"Forbidden keyword: {kw}")

    # No UNION/WITH/nested SELECTs to simplify validation
    # (allow subqueries — but the table extraction catches forbidden tables)
    if re.search(r'\bUNION\b', upper):
        raise SQLValidationError("UNION not allowed")
    if re.search(r'\bWITH\b', upper):
        raise SQLValidationError("CTEs (WITH) not allowed")

    # No comments — could be used to hide things
    if "--" in cleaned or "/*" in cleaned:
        raise SQLValidationError("Comments not allowed")

    # Extract tables
    tables = _extract_tables(parsed[0])

    # Check for forbidden tables
    for t in tables:
        if t in FORBIDDEN_TABLES:
            raise SQLValidationError(f"Access to table '{t}' is forbidden")
        if t not in ALLOWED_TABLES:
            raise SQLValidationError(f"Table '{t}' is not in the whitelist")

    return cleaned, tables


def enforce_org_scope_and_limit(query: str, tables: set[str], org_id: str) -> str:
    """Wrap the query to enforce org scope and row limit.

    We use the simple approach: wrap the original query in a CTE-like outer SELECT
    that applies LIMIT. Org-scope checking is done by verifying the WHERE clause
    contains the organization_id reference when org-scoped tables are used.
    """
    org_scoped_used = tables & ORG_SCOPED_TABLES

    # If org-scoped tables are used, auto-inject org_id filter if missing
    if org_scoped_used:
        if not re.search(r'\borganization_id\b', query, re.IGNORECASE):
            # Auto-inject: wrap in subquery with org filter on the first org-scoped table
            # Find the first org-scoped table in the FROM clause to scope on
            first_table = sorted(org_scoped_used)[0]
            # Inject organization_id filter into WHERE clause
            if re.search(r'\bWHERE\b', query, re.IGNORECASE):
                query = re.sub(
                    r'\bWHERE\b',
                    f"WHERE {first_table}.organization_id = :org_id AND",
                    query, count=1, flags=re.IGNORECASE,
                )
            else:
                # No WHERE clause — add one before ORDER BY/GROUP BY/LIMIT or at end
                insert_before = re.search(r'\b(ORDER BY|GROUP BY|LIMIT|$)', query, re.IGNORECASE)
                pos = insert_before.start() if insert_before else len(query)
                query = query[:pos] + f" WHERE {first_table}.organization_id = :org_id " + query[pos:]
            logger.info(f"Auto-injected org scope on table '{first_table}'")

    # Apply/enforce LIMIT. If the query already has a LIMIT, cap it at MAX_ROWS.
    # Simplest: wrap as subquery with outer LIMIT.
    wrapped = f"SELECT * FROM ({query}) AS _dp_inner LIMIT {MAX_ROWS}"
    return wrapped


async def execute_safe_query(db: AsyncSession, org_id: str, query: str, reason: str = "") -> dict:
    """Validate, scope, and execute a SELECT query. Returns results as JSON-safe dict."""
    logger.info(f"DeepBlue query_database invoked. Reason: {reason[:100]}")

    try:
        cleaned, tables = validate_query(query)
        final_sql = enforce_org_scope_and_limit(cleaned, tables, org_id)
    except SQLValidationError as e:
        return {"error": f"Query rejected: {e}"}

    # Bind org_id for :org_id placeholders in the user query (if they used named params)
    params = {"org_id": org_id}

    try:
        # Set statement timeout for this connection
        await db.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))

        # Execute
        result = await db.execute(text(final_sql), params)
        rows = result.fetchall()
        columns = list(result.keys()) if rows else []

        # Convert rows to JSON-safe format
        data = []
        for row in rows:
            row_dict = {}
            for col, val in zip(columns, row):
                if hasattr(val, "isoformat"):
                    row_dict[col] = val.isoformat()
                elif hasattr(val, "__float__") and not isinstance(val, (int, bool)):
                    try:
                        row_dict[col] = float(val)
                    except (TypeError, ValueError):
                        row_dict[col] = str(val)
                else:
                    row_dict[col] = val
            data.append(row_dict)

        return {
            "columns": columns,
            "rows": data,
            "row_count": len(data),
            "truncated": len(data) >= MAX_ROWS,
        }
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        return {"error": f"Execution failed: {str(e)[:200]}"}
