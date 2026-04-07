"""DeepBlue tool definitions and executor dispatcher.

Tools are defined in Anthropic tool_use schema format.
Each tool has an async executor in a domain-specific module.
"""

import json
import logging

from .tools_common import ToolContext, MAX_PARTS_SEARCHES_PER_TURN  # noqa: F401 — re-exported

from .tools_chemistry import EXECUTORS as _chem
from .tools_equipment import EXECUTORS as _equip
from .tools_customer import EXECUTORS as _customer
from .tools_operations import EXECUTORS as _ops
from .tools_billing import EXECUTORS as _billing
from .tools_communication import EXECUTORS as _comms
from .tools_admin import EXECUTORS as _admin

logger = logging.getLogger(__name__)


# ── Tool Definitions (Anthropic schema) ──────────────────────────────

TOOLS = [
    {
        "name": "chemical_dosing_calculator",
        "description": (
            "Calculate exact chemical dosing amounts for a pool. Provide the current readings "
            "and pool volume. Returns precise amounts of each chemical needed to reach target levels. "
            "Use this for ANY dosing question — never guess chemical amounts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pool_gallons": {"type": "integer", "description": "Pool volume in gallons"},
                "ph": {"type": "number", "description": "Current pH reading (e.g., 7.2)"},
                "free_chlorine": {"type": "number", "description": "Current free chlorine in ppm"},
                "alkalinity": {"type": "integer", "description": "Current total alkalinity in ppm"},
                "calcium_hardness": {"type": "integer", "description": "Current calcium hardness in ppm"},
                "cyanuric_acid": {"type": "integer", "description": "Current CYA/stabilizer in ppm"},
                "combined_chlorine": {"type": "number", "description": "Current combined chlorine in ppm"},
                "phosphates": {"type": "integer", "description": "Current phosphates in ppb"},
            },
            "required": ["pool_gallons"],
        },
    },
    {
        "name": "get_equipment",
        "description": (
            "Get all equipment installed on a property or specific water feature (pool/spa). "
            "Returns equipment type, brand, model, and linked catalog info. "
            "Use the context IDs if available — you don't need to ask the user for property/WF ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Property ID (uses context if not provided)"},
                "bow_id": {"type": "string", "description": "Body of water ID (uses context if not provided)"},
            },
        },
    },
    {
        "name": "find_replacement_parts",
        "description": (
            "Search for replacement parts for equipment. Two modes: "
            "'find_parts' (default) returns a list of matching parts with prices and vendor links; "
            "'compare_retailers' returns the SAME part priced across multiple vendors for comparison. "
            "Use compare_retailers when the user asks 'where can I buy', 'compare prices', 'which retailer', etc. "
            "IMPORTANT: if you don't have a specific equipment model, use get_equipment first to look up the installed equipment. "
            "Never search for generic terms like 'pump' — always use a specific brand and model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "equipment_model": {"type": "string", "description": "Specific model name with brand (e.g., 'Pentair IntelliFlo VSF 3050'). Required."},
                "equipment_type": {"type": "string", "description": "Equipment type (pump, filter, heater, booster_pump, etc.)"},
                "part_description": {"type": "string", "description": "Optional: specific part to find (e.g., 'front seal plate', 'impeller', 'O-ring kit')"},
                "mode": {
                    "type": "string",
                    "enum": ["find_parts", "compare_retailers"],
                    "description": "find_parts (default) or compare_retailers for price comparison",
                },
                "max_price": {"type": "number", "description": "Optional budget cap in USD"},
                "limit": {"type": "integer", "description": "Max results (default 3, max 5)"},
            },
            "required": ["equipment_model", "equipment_type"],
        },
    },
    {
        "name": "get_chemical_history",
        "description": (
            "Get recent chemical readings for a property or body of water. "
            "Returns the last several readings with dates and all chemical values."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Property ID (uses context if not provided)"},
                "bow_id": {"type": "string", "description": "Body of water ID (uses context if not provided)"},
                "limit": {"type": "integer", "description": "Number of readings to return (default 10)"},
            },
        },
    },
    {
        "name": "get_service_history",
        "description": (
            "Get recent service visits for a property. "
            "Returns visit dates, technician, duration, and notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Property ID (uses context if not provided)"},
                "limit": {"type": "integer", "description": "Number of visits to return (default 10)"},
            },
        },
    },
    {
        "name": "search_equipment_catalog",
        "description": (
            "Search the shared equipment catalog by keyword, type, or manufacturer. "
            "Returns matching equipment with specs and linked parts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term (model name, brand, type)"},
                "equipment_type": {"type": "string", "description": "Filter by type: pump, filter, heater, chlorinator, valve, cleaner, blower, control, other"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_customer_info",
        "description": (
            "Get full customer details including properties, billing, contact info, and service schedule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
            },
        },
    },
    {
        "name": "find_customer",
        "description": (
            "Fuzzy search for customers by ANY text fragment — name, management company, email, phone, or partial. "
            "Searches: display_name, company_name, first_name, last_name, email, phone, plus property address/name. "
            "Use this FIRST when the user mentions a customer by any partial identifier. "
            "When searching for a management company (e.g., 'BLVD', 'WestCal'), use just the company name — not 'all BLVD'. "
            "Increase limit to 50 when you expect many results (e.g., all clients under a management company). "
            "Never ask the user for a customer ID — use this tool to resolve partial info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text fragment to search (e.g., 'lew', 'BLVD', 'westcal', 'brightpm')"},
                "limit": {"type": "integer", "description": "Max results (default 10, max 50)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_property",
        "description": (
            "Fuzzy search for properties by address, property name, or city. Use this when the user mentions "
            "a location fragment, pool nickname, or address piece. Returns property with its bodies of water so "
            "you can find the right pool/spa. Never ask for a property ID — use this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Address fragment, property name, or city"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_billing_documents",
        "description": (
            "List invoices or estimates for a customer (or the whole org). "
            "Set document_type to 'invoice' for invoices, 'estimate' for estimates, or 'all' for both."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "document_type": {
                    "type": "string",
                    "enum": ["invoice", "estimate", "all"],
                    "description": "Filter by document type. Default: 'invoice'",
                },
                "status": {"type": "string", "description": "Filter by status (e.g., draft, sent, paid, overdue)"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
        },
    },
    {
        "name": "get_open_jobs",
        "description": "List open/in-progress jobs (agent_actions) for a customer or the whole org. Filter by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "status": {"type": "string", "description": "open, in_progress, pending_approval, done, suggested"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
        },
    },
    {
        "name": "get_cases",
        "description": "List service cases for a customer or recent. Cases group related jobs, invoices, and communications.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "status": {"type": "string", "description": "new, triaging, scoping, in_progress, pending_payment, closed"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
        },
    },
    {
        "name": "get_routes_today",
        "description": "Get today's routes for all techs, with stop counts and properties. Use for 'where are techs today' or 'how many stops for Brian'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tech_id": {"type": "string", "description": "Optional: filter to a specific tech"},
            },
        },
    },
    {
        "name": "get_techs",
        "description": "List all active technicians with contact info, hourly rate, and working days.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_billing_terms",
        "description": "Get the organization's billing terms: payment terms days, labor rate, estimate validity, late fee percentage, warranty days.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_service_tiers",
        "description": "List residential service tier packages with base rates and included services.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_inspections",
        "description": "Get inspection history for a property (matched health department inspections). Returns violations, inspector, dates, closure status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Property ID (uses context if not provided)"},
                "limit": {"type": "integer", "description": "Max inspections (default 5)"},
            },
        },
    },
    {
        "name": "get_payments",
        "description": "Payment history for a customer, or recent payments org-wide. Returns amounts, methods, dates, and linked invoices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
        },
    },
    {
        "name": "query_database",
        "description": (
            "LAST RESORT: run a read-only SQL SELECT against the database when no specific tool fits. "
            "Use this ONLY when no other tool can answer the question. Prefer specific tools (get_invoices, get_open_jobs, etc) first. "
            "Query must be a single SELECT statement. Org scope is automatically enforced. Results capped at 100 rows. "
            "Available tables (org-scoped): customers, properties, water_features, equipment_items, visits, chemical_readings, "
            "invoices, invoice_line_items, payments, agent_actions, agent_threads, agent_messages, service_cases, routes, route_stops, "
            "techs, broadcast_emails, feedback_items, customer_contacts. "
            "Shared tables: equipment_catalog, parts_catalog, inspection_facilities, inspections, inspection_violations, service_tiers, bather_load_jurisdictions. "
            "When querying org-scoped tables, include `organization_id = '<org>'` — the system auto-fills this but your WHERE clause must allow it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single SELECT statement. No INSERT/UPDATE/DELETE/DDL. Use LIMIT."},
                "reason": {"type": "string", "description": "Why no specific tool fits (1 sentence)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_agent_health",
        "description": (
            "Get AI agent health metrics: success rate, total calls, cost, failures, per-agent breakdown. "
            "Use when the user asks how the agents are doing, if anything is broken, recent failures, or agent costs. "
            "Returns metrics for the last 24 hours by default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Time window in hours (default 24)"},
                "agent_name": {"type": "string", "description": "Optional: filter to one agent (email_classifier, customer_matcher, deepblue, etc.)"},
            },
        },
    },
    {
        "name": "get_organization_info",
        "description": (
            "Get the organization's own profile: name, phone, email, addresses (mailing/physical/billing), "
            "and branding. Use this when drafting communications that reference the company's own address, "
            "phone, or contact info (like 'our new mailing address' or 'contact us at')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_equipment_to_pool",
        "description": (
            "Add a piece of equipment (pump, filter, heater, etc.) to a specific body of water. "
            "Returns a preview — the user must confirm before it's saved. "
            "Use find_property first to get the bow_id if you don't have it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bow_id": {"type": "string", "description": "Body of water ID (use find_property to get this)"},
                "equipment_type": {"type": "string", "description": "Type: pump, filter, heater, chlorinator, valve, cleaner, blower, control, booster_pump, other"},
                "brand": {"type": "string", "description": "Manufacturer (e.g., 'Polaris', 'Pentair')"},
                "model": {"type": "string", "description": "Model name or number (e.g., 'PB4-60')"},
                "notes": {"type": "string", "description": "Optional notes about this equipment"},
            },
            "required": ["bow_id", "equipment_type", "brand", "model"],
        },
    },
    {
        "name": "log_chemical_reading",
        "description": (
            "Record a chemical reading for a property or specific body of water. Returns a preview — user must confirm. "
            "All fields optional except property_id. At least one chemical value should be provided."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Property ID (uses context if not provided)"},
                "bow_id": {"type": "string", "description": "Optional body of water ID"},
                "ph": {"type": "number"},
                "free_chlorine": {"type": "number"},
                "combined_chlorine": {"type": "number"},
                "alkalinity": {"type": "integer"},
                "calcium_hardness": {"type": "integer"},
                "cyanuric_acid": {"type": "integer"},
                "phosphates": {"type": "integer"},
                "water_temp": {"type": "number"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "update_customer_note",
        "description": (
            "Append a note to a customer's profile. Does not replace existing notes. Returns a preview — user must confirm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "note_text": {"type": "string", "description": "The note to append"},
            },
            "required": ["note_text"],
        },
    },
    {
        "name": "draft_broadcast_email",
        "description": (
            "Draft a bulk email for review. Use for announcements, address changes, seasonal notices, etc. "
            "Returns a preview with recipient count — the user must confirm before it sends. "
            "Recipient options: all active customers, commercial only, residential only, a specific list of customer IDs, "
            "or a test send to a single address (for previewing). "
            "IMPORTANT: when the user names specific customers, first resolve those names to customer IDs using "
            "get_customer_info or query_database, then pass the IDs in customer_ids."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text. Professional, concise. Use \\n\\n for paragraph breaks, \\n for single line breaks. Do not include markdown formatting."},
                "filter_type": {
                    "type": "string",
                    "enum": ["all_active", "commercial", "residential", "custom", "test"],
                    "description": "all_active=everyone, commercial=commercial only, residential=residential only, custom=specific customer list, test=single preview email",
                },
                "customer_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Customer IDs when filter_type='custom'. Required for custom filter.",
                },
                "test_recipient": {
                    "type": "string",
                    "description": "Email address for filter_type='test'. If not provided, uses the current user's email.",
                },
            },
            "required": ["subject", "body", "filter_type"],
        },
    },
    {
        "name": "draft_customer_email",
        "description": (
            "Draft an email to a specific customer for review. Use when the user wants to email "
            "the customer they're currently looking at (from a case, thread, or customer page). "
            "Returns a preview — the user must confirm before it sends. "
            "Do NOT use draft_broadcast_email for single-customer emails — use this instead. "
            "The customer's email is resolved automatically from context — never ask the user for it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text. Professional, concise. Use \\n\\n for paragraph breaks. No markdown."},
                "customer_id": {"type": "string", "description": "Customer ID. Use context if available — don't ask the user."},
            },
            "required": ["subject", "body"],
        },
    },
]


# ── Merged Executor Registry ────────────────────────────────────────

_EXECUTORS = {**_chem, **_equip, **_customer, **_ops, **_billing, **_comms, **_admin}


# ── Tool Dispatcher ─────────────────────────────────────────────────

async def execute_tool(tool_name: str, tool_input: dict, ctx: ToolContext) -> str:
    """Route a tool call to its executor. Returns JSON string result.

    Errors are always logged internally and returned with a semantic message
    plus a retry_hint for Claude. Never surface raw exceptions.
    """
    try:
        executor = _EXECUTORS.get(tool_name)
        if not executor:
            return json.dumps({
                "error": f"Tool '{tool_name}' not available",
                "retry_hint": "Use one of the available tools listed in your system prompt.",
            })
        result = await executor(tool_input, ctx)
        return json.dumps(result, default=str)
    except Exception as e:
        error_str = str(e)
        logger.error(f"Tool execution failed [{tool_name}]: {error_str}", exc_info=True)
        # Rollback to clear any poisoned transaction state so subsequent tool calls work
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        # Semantic user-safe error + instructive hint for Claude
        return json.dumps({
            "error": "This lookup didn't work.",
            "retry_hint": (
                "Try a different approach: use a different search tool, broaden your query, "
                "or use query_database with explicit org scoping. Never show error text to the user."
            ),
        })
