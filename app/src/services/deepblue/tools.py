"""DeepBlue tool definitions and executors.

Tools are defined in Anthropic tool_use schema format.
Each tool has an async executor that receives tool_input + a ToolContext.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: AsyncSession
    org_id: str
    customer_id: str | None = None
    property_id: str | None = None
    bow_id: str | None = None
    visit_id: str | None = None


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
            "Get all equipment installed on a property or specific body of water (pool/spa). "
            "Returns equipment type, brand, model, and linked catalog info. "
            "Use the context IDs if available — you don't need to ask the user for property/BOW ID."
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
            "Search for replacement parts for a specific piece of equipment. "
            "Provide the equipment type and model name. Returns parts with names, SKUs, and prices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "equipment_model": {"type": "string", "description": "Equipment model name (e.g., 'Pentair IntelliFlo VSF')"},
                "equipment_type": {"type": "string", "description": "Equipment type (pump, filter, heater, etc.)"},
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
        "name": "get_invoices",
        "description": "List invoices for a customer or recent invoices for the org. Filter by status or document type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "status": {"type": "string", "description": "draft, sent, paid, overdue, void, written_off"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
        },
    },
    {
        "name": "get_estimates",
        "description": "List estimates for a customer or recent. Same as get_invoices but filtered to document_type='estimate'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID (uses context if not provided)"},
                "status": {"type": "string", "description": "draft, sent, approved, declined, expired"},
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
]


# ── Tool Executors ────────────────────────────────────────────────────

async def execute_tool(tool_name: str, tool_input: dict, ctx: ToolContext) -> str:
    """Route a tool call to its executor. Returns JSON string result."""
    try:
        executor = _EXECUTORS.get(tool_name)
        if not executor:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        result = await executor(tool_input, ctx)
        return json.dumps(result, default=str)
    except Exception as e:
        logger.error(f"Tool execution failed [{tool_name}]: {e}")
        return json.dumps({"error": f"Tool failed: {str(e)}"})


async def _exec_dosing(inp: dict, ctx: ToolContext) -> dict:
    """Deterministic chemical dosing calculator."""
    from src.services.dosing_engine import calculate_dosing
    return calculate_dosing(
        pool_gallons=inp.get("pool_gallons", 15000),
        ph=inp.get("ph"),
        free_chlorine=inp.get("free_chlorine"),
        alkalinity=inp.get("alkalinity"),
        calcium_hardness=inp.get("calcium_hardness"),
        cyanuric_acid=inp.get("cyanuric_acid"),
        combined_chlorine=inp.get("combined_chlorine"),
        phosphates=inp.get("phosphates"),
    )


async def _exec_get_equipment(inp: dict, ctx: ToolContext) -> dict:
    """Get equipment installed on a property/BOW."""
    from src.models.equipment_item import EquipmentItem
    from src.models.water_feature import WaterFeature

    bow_id = inp.get("bow_id") or ctx.bow_id
    property_id = inp.get("property_id") or ctx.property_id

    if not bow_id and not property_id:
        return {"error": "No property or body of water in context. Ask which property."}

    query = select(EquipmentItem).options(
        selectinload(EquipmentItem.catalog_equipment)
    ).where(EquipmentItem.is_active == True)

    if bow_id:
        query = query.where(EquipmentItem.water_feature_id == bow_id)
    elif property_id:
        wf_ids = (await ctx.db.execute(
            select(WaterFeature.id).where(WaterFeature.property_id == property_id, WaterFeature.is_active == True)
        )).scalars().all()
        if not wf_ids:
            return {"equipment": [], "message": "No bodies of water found for this property."}
        query = query.where(EquipmentItem.water_feature_id.in_(wf_ids))

    items = (await ctx.db.execute(query)).scalars().all()
    return {
        "equipment": [
            {
                "type": ei.equipment_type,
                "brand": ei.brand,
                "model": ei.model,
                "name": (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                         ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip()),
                "catalog_id": ei.catalog_equipment_id,
            }
            for ei in items
        ]
    }


async def _exec_find_parts(inp: dict, ctx: ToolContext) -> dict:
    """Find replacement parts for equipment. Checks internal catalog first, falls back to web search."""
    from src.models.parts_catalog import PartsCatalog
    from src.models.equipment_catalog import EquipmentCatalog

    model = inp.get("equipment_model", "")
    eq_type = inp.get("equipment_type", "")

    # Search catalog for matching equipment
    equip = (await ctx.db.execute(
        select(EquipmentCatalog).where(
            EquipmentCatalog.canonical_name.ilike(f"%{model}%"),
        ).limit(3)
    )).scalars().all()

    if not equip and model:
        # Try broader search
        first_word = model.split()[0] if model.split() else ""
        if first_word:
            equip = (await ctx.db.execute(
                select(EquipmentCatalog).where(
                    EquipmentCatalog.equipment_type == eq_type,
                    EquipmentCatalog.manufacturer.ilike(f"%{first_word}%"),
                ).limit(5)
            )).scalars().all()

    catalog_parts = []
    equipment_matched = None
    if equip:
        equipment_matched = equip[0].canonical_name
        catalog_ids = [e.id for e in equip]
        parts = (await ctx.db.execute(
            select(PartsCatalog).where(PartsCatalog.for_equipment_id.in_(catalog_ids)).limit(20)
        )).scalars().all()
        catalog_parts = [
            {
                "name": p.name,
                "sku": p.sku,
                "brand": p.brand,
                "category": p.category,
                "vendor": p.vendor_provider,
                "source": "catalog",
            }
            for p in parts
        ]

    # If catalog has few/no results, search the web
    web_results = []
    if len(catalog_parts) < 3:
        try:
            from src.services.parts.web_search_agent import PartsWebSearchAgent
            agent = PartsWebSearchAgent()
            search_query = f"{model} {eq_type} replacement parts".strip()
            web_data = await agent.search(search_query, max_results=5)
            web_results = [
                {
                    "name": r.get("product_name", ""),
                    "price": r.get("price"),
                    "vendor": r.get("vendor_name", ""),
                    "url": r.get("vendor_url", ""),
                    "source": "web_search",
                }
                for r in web_data.get("web_results", [])
            ]
        except Exception as e:
            logger.warning(f"Web parts search failed: {e}")

    return {
        "equipment_matched": equipment_matched,
        "catalog_parts": catalog_parts,
        "web_results": web_results,
        "message": None if (catalog_parts or web_results) else f"No parts found for '{model}'.",
    }


async def _exec_chemical_history(inp: dict, ctx: ToolContext) -> dict:
    """Get recent chemical readings."""
    from src.models.chemical_reading import ChemicalReading

    bow_id = inp.get("bow_id") or ctx.bow_id
    property_id = inp.get("property_id") or ctx.property_id
    limit = inp.get("limit", 10)

    if not bow_id and not property_id:
        return {"error": "No property or body of water in context."}

    query = select(ChemicalReading).order_by(desc(ChemicalReading.created_at)).limit(limit)
    if bow_id:
        query = query.where(ChemicalReading.body_of_water_id == bow_id)
    elif property_id:
        query = query.where(ChemicalReading.property_id == property_id)

    readings = (await ctx.db.execute(query)).scalars().all()
    return {
        "readings": [
            {
                "date": r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
                "ph": r.ph, "free_chlorine": r.free_chlorine,
                "combined_chlorine": r.combined_chlorine,
                "alkalinity": r.alkalinity, "calcium_hardness": r.calcium_hardness,
                "cyanuric_acid": r.cyanuric_acid, "phosphates": r.phosphates,
                "water_temp": r.water_temp,
            }
            for r in readings
        ],
    }


async def _exec_service_history(inp: dict, ctx: ToolContext) -> dict:
    """Get recent service visits."""
    from src.models.visit import Visit

    property_id = inp.get("property_id") or ctx.property_id
    limit = inp.get("limit", 10)

    if not property_id:
        return {"error": "No property in context."}

    visits = (await ctx.db.execute(
        select(Visit).where(Visit.property_id == property_id)
        .order_by(desc(Visit.scheduled_date)).limit(limit)
    )).scalars().all()

    return {
        "visits": [
            {
                "date": v.scheduled_date.strftime("%Y-%m-%d") if v.scheduled_date else None,
                "tech": v.tech_id,
                "duration_minutes": v.duration_minutes,
                "status": v.status,
                "notes": v.notes[:200] if v.notes else None,
            }
            for v in visits
        ],
    }


async def _exec_search_catalog(inp: dict, ctx: ToolContext) -> dict:
    """Search equipment catalog."""
    from src.models.equipment_catalog import EquipmentCatalog

    query_str = inp.get("query", "")
    eq_type = inp.get("equipment_type")

    q = select(EquipmentCatalog).where(
        EquipmentCatalog.canonical_name.ilike(f"%{query_str}%"),
    )
    if eq_type:
        q = q.where(EquipmentCatalog.equipment_type == eq_type)
    q = q.limit(10)

    results = (await ctx.db.execute(q)).scalars().all()
    return {
        "results": [
            {
                "id": e.id,
                "name": e.canonical_name,
                "manufacturer": e.manufacturer,
                "type": e.equipment_type,
                "model": getattr(e, "model_number", None),
            }
            for e in results
        ],
    }


async def _exec_customer_info(inp: dict, ctx: ToolContext) -> dict:
    """Get full customer details."""
    from src.models.customer import Customer
    from src.models.property import Property

    customer_id = inp.get("customer_id") or ctx.customer_id
    if not customer_id:
        return {"error": "No customer in context."}

    cust = (await ctx.db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == ctx.org_id)
    )).scalar_one_or_none()
    if not cust:
        return {"error": "Customer not found."}

    props = (await ctx.db.execute(
        select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
    )).scalars().all()

    return {
        "name": cust.display_name,
        "type": cust.customer_type,
        "company": cust.company_name,
        "email": cust.email,
        "phone": cust.phone,
        "monthly_rate": float(cust.monthly_rate) if cust.monthly_rate else None,
        "service_days": cust.preferred_day,
        "status": "active" if cust.is_active else "inactive",
        "properties": [
            {"id": p.id, "name": p.name, "address": p.full_address}
            for p in props
        ],
    }


async def _exec_org_info(inp: dict, ctx: ToolContext) -> dict:
    """Get the organization's own profile (name, phone, addresses, branding)."""
    from src.models.organization import Organization

    org = (await ctx.db.execute(
        select(Organization).where(Organization.id == ctx.org_id)
    )).scalar_one_or_none()
    if not org:
        return {"error": "Organization not found"}

    # Parse structured addresses and resolve same_as references
    addresses = {}
    if org.addresses:
        try:
            raw = json.loads(org.addresses)
            # Resolve same_as references
            resolved = {}
            for key, val in raw.items():
                if isinstance(val, dict) and "same_as" in val:
                    source = raw.get(val["same_as"], {})
                    if isinstance(source, dict) and "same_as" not in source:
                        resolved[key] = {**source, "_same_as": val["same_as"]}
                    else:
                        resolved[key] = val
                else:
                    resolved[key] = val
            addresses = resolved
        except json.JSONDecodeError:
            pass

    # Fallback to flat fields if no structured addresses
    if not addresses and (org.address or org.city):
        addresses = {
            "mailing": {
                "street": org.address or "",
                "city": org.city or "",
                "state": org.state or "",
                "zip": org.zip_code or "",
            }
        }

    return {
        "name": org.name,
        "phone": org.phone,
        "email": org.email,
        "tagline": org.tagline,
        "addresses": addresses,
        "service_area": org.agent_service_area,
        "billing_email": org.billing_email,
    }


async def _exec_get_invoices(inp: dict, ctx: ToolContext, doc_type: str = "invoice") -> dict:
    from src.models.invoice import Invoice

    query = select(Invoice).where(
        Invoice.organization_id == ctx.org_id,
        Invoice.document_type == doc_type,
    )
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(Invoice.customer_id == cust_id)
    if inp.get("status"):
        query = query.where(Invoice.status == inp["status"])
    query = query.order_by(desc(Invoice.issue_date)).limit(inp.get("limit", 10))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "results": [
            {
                "id": r.id,
                "number": r.invoice_number,
                "status": r.status,
                "subject": r.subject,
                "total": float(r.total or 0),
                "balance": float(r.balance or 0),
                "issue_date": r.issue_date.isoformat() if r.issue_date else None,
                "due_date": r.due_date.isoformat() if r.due_date else None,
            }
            for r in rows
        ],
    }


async def _exec_get_estimates(inp: dict, ctx: ToolContext) -> dict:
    return await _exec_get_invoices(inp, ctx, doc_type="estimate")


async def _exec_get_open_jobs(inp: dict, ctx: ToolContext) -> dict:
    from src.models.agent_action import AgentAction

    query = select(AgentAction).where(AgentAction.organization_id == ctx.org_id)
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(AgentAction.customer_id == cust_id)
    if inp.get("status"):
        query = query.where(AgentAction.status == inp["status"])
    else:
        query = query.where(AgentAction.status.in_(("open", "in_progress", "pending_approval")))
    query = query.order_by(desc(AgentAction.created_at)).limit(inp.get("limit", 20))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "jobs": [
            {
                "id": r.id,
                "type": r.action_type,
                "description": r.description,
                "status": r.status,
                "assigned_to": r.assigned_to,
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "is_suggested": r.is_suggested,
            }
            for r in rows
        ],
    }


async def _exec_get_cases(inp: dict, ctx: ToolContext) -> dict:
    from src.models.service_case import ServiceCase

    query = select(ServiceCase).where(ServiceCase.organization_id == ctx.org_id)
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(ServiceCase.customer_id == cust_id)
    if inp.get("status"):
        query = query.where(ServiceCase.status == inp["status"])
    query = query.order_by(desc(ServiceCase.updated_at)).limit(inp.get("limit", 10))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "cases": [
            {
                "case_number": r.case_number,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                "invoice_count": r.invoice_count,
                "total_invoiced": float(r.total_invoiced or 0),
                "total_paid": float(r.total_paid or 0),
            }
            for r in rows
        ],
    }


async def _exec_get_routes_today(inp: dict, ctx: ToolContext) -> dict:
    from datetime import date
    from src.models.route import Route
    from src.models.route_stop import RouteStop
    from src.models.tech import Tech
    from src.models.property import Property

    # "service_day" is day-of-week name; match today's weekday
    weekday_name = date.today().strftime("%A")

    query = select(Route).where(
        Route.organization_id == ctx.org_id,
        Route.service_day == weekday_name,
    )
    if inp.get("tech_id"):
        query = query.where(Route.tech_id == inp["tech_id"])

    routes = (await ctx.db.execute(query)).scalars().all()

    result = []
    for r in routes:
        tech = (await ctx.db.execute(select(Tech).where(Tech.id == r.tech_id))).scalar_one_or_none()
        stops = (await ctx.db.execute(
            select(RouteStop).where(RouteStop.route_id == r.id).order_by(RouteStop.sequence)
        )).scalars().all()
        stop_list = []
        for s in stops:
            prop = (await ctx.db.execute(select(Property).where(Property.id == s.property_id))).scalar_one_or_none()
            stop_list.append({
                "sequence": s.sequence,
                "property": prop.full_address if prop else None,
                "eta": str(s.estimated_arrival_time) if s.estimated_arrival_time else None,
            })
        result.append({
            "tech_name": f"{tech.first_name} {tech.last_name}" if tech else "Unknown",
            "total_stops": r.total_stops,
            "total_duration_minutes": r.total_duration_minutes,
            "total_distance_miles": r.total_distance_miles,
            "stops": stop_list,
        })

    return {"date": weekday_name, "routes": result}


async def _exec_get_techs(inp: dict, ctx: ToolContext) -> dict:
    from src.models.tech import Tech

    rows = (await ctx.db.execute(
        select(Tech).where(Tech.organization_id == ctx.org_id, Tech.is_active == True)
    )).scalars().all()
    return {
        "techs": [
            {
                "id": t.id,
                "name": f"{t.first_name} {t.last_name}",
                "email": t.email,
                "phone": t.phone,
                "hourly_rate": float(t.hourly_rate) if t.hourly_rate else None,
                "job_title": t.job_title,
                "working_days": t.working_days,
                "start_address": t.start_address,
            }
            for t in rows
        ],
    }


async def _exec_get_billing_terms(inp: dict, ctx: ToolContext) -> dict:
    from src.models.org_cost_settings import OrgCostSettings

    settings = (await ctx.db.execute(
        select(OrgCostSettings).where(OrgCostSettings.organization_id == ctx.org_id)
    )).scalar_one_or_none()
    if not settings:
        return {"error": "No billing settings configured"}

    return {
        "payment_terms_days": settings.payment_terms_days,
        "estimate_validity_days": settings.estimate_validity_days,
        "late_fee_pct": float(settings.late_fee_pct or 0),
        "warranty_days": settings.warranty_days,
        "billable_labor_rate": float(settings.billable_labor_rate or 0),
        "default_parts_markup_pct": float(settings.default_parts_markup_pct or 0),
        "auto_approve_threshold": float(settings.auto_approve_threshold or 0),
        "separate_invoice_threshold": float(settings.separate_invoice_threshold or 0),
        "estimate_terms": settings.estimate_terms,
    }


async def _exec_get_service_tiers(inp: dict, ctx: ToolContext) -> dict:
    from src.models.service_tier import ServiceTier

    rows = (await ctx.db.execute(
        select(ServiceTier).where(
            ServiceTier.organization_id == ctx.org_id,
            ServiceTier.is_active == True,
        ).order_by(ServiceTier.sort_order)
    )).scalars().all()
    return {
        "tiers": [
            {
                "name": t.name,
                "base_rate": float(t.base_rate or 0),
                "estimated_minutes": t.estimated_minutes,
                "is_default": t.is_default,
                "description": t.description,
                "includes": [
                    k.replace("includes_", "")
                    for k in ("includes_chems", "includes_skim", "includes_baskets",
                              "includes_vacuum", "includes_brush", "includes_equipment_check")
                    if getattr(t, k, False)
                ],
            }
            for t in rows
        ],
    }


async def _exec_get_inspections(inp: dict, ctx: ToolContext) -> dict:
    from src.models.inspection_facility import InspectionFacility
    from src.models.inspection import Inspection
    from src.models.inspection_violation import InspectionViolation

    property_id = inp.get("property_id") or ctx.property_id
    if not property_id:
        return {"error": "No property in context. Specify a property_id."}

    facility = (await ctx.db.execute(
        select(InspectionFacility).where(InspectionFacility.matched_property_id == property_id)
    )).scalar_one_or_none()
    if not facility:
        return {"inspections": [], "message": "This property has no matched inspection facility."}

    limit = inp.get("limit", 5)
    inspections = (await ctx.db.execute(
        select(Inspection).where(Inspection.facility_id == facility.id)
        .order_by(desc(Inspection.inspection_date)).limit(limit)
    )).scalars().all()

    result = []
    for i in inspections:
        violations = (await ctx.db.execute(
            select(InspectionViolation).where(InspectionViolation.inspection_id == i.id)
        )).scalars().all()
        result.append({
            "date": i.inspection_date.isoformat() if i.inspection_date else None,
            "type": i.inspection_type,
            "inspector": i.inspector_name,
            "total_violations": i.total_violations,
            "major_violations": i.major_violations,
            "closure_status": i.closure_status,
            "closure_required": i.closure_required,
            "reinspection_required": i.reinspection_required,
            "violations": [
                {"description": v.description[:200] if v.description else None, "is_major": v.is_major}
                for v in violations[:10]
            ],
        })

    return {
        "facility": {
            "name": facility.name,
            "address": f"{facility.street_address}, {facility.city}" if facility.street_address else None,
            "permit_holder": facility.permit_holder,
        },
        "inspections": result,
    }


async def _exec_get_payments(inp: dict, ctx: ToolContext) -> dict:
    from src.models.payment import Payment

    query = select(Payment).where(Payment.organization_id == ctx.org_id)
    cust_id = inp.get("customer_id") or ctx.customer_id
    if cust_id:
        query = query.where(Payment.customer_id == cust_id)
    query = query.order_by(desc(Payment.payment_date)).limit(inp.get("limit", 10))

    rows = (await ctx.db.execute(query)).scalars().all()
    return {
        "payments": [
            {
                "amount": float(r.amount or 0),
                "method": r.payment_method,
                "date": r.payment_date.isoformat() if r.payment_date else None,
                "status": r.status,
                "reference": r.reference_number,
                "invoice_id": r.invoice_id,
            }
            for r in rows
        ],
    }


async def _exec_query_database(inp: dict, ctx: ToolContext) -> dict:
    """Meta-tool: run a validated, read-only, org-scoped SELECT query."""
    from src.services.deepblue.sql_executor import execute_safe_query
    try:
        return await execute_safe_query(
            db=ctx.db,
            org_id=ctx.org_id,
            query=inp.get("query", ""),
            reason=inp.get("reason", ""),
        )
    except Exception as e:
        logger.error(f"query_database failed: {e}")
        return {"error": str(e)}


async def _exec_broadcast(inp: dict, ctx: ToolContext) -> dict:
    """Draft a broadcast email — returns preview. Does NOT send yet."""
    from src.services.broadcast_service import BroadcastService
    from src.models.customer import Customer

    subject = inp.get("subject", "")
    body = inp.get("body", "")
    filter_type = inp.get("filter_type", "all_active")
    customer_ids = inp.get("customer_ids") or []
    test_recipient = inp.get("test_recipient")

    if not subject or not body:
        return {"error": "Subject and body are required."}

    # Test send — single recipient preview
    if filter_type == "test":
        return {
            "action": "broadcast_email",
            "requires_confirmation": True,
            "preview": {
                "subject": subject,
                "body": body,
                "filter_type": "test",
                "filter_label": f"Test send to {test_recipient or 'your email'}",
                "test_recipient": test_recipient,
                "recipient_count": 1,
                "customer_names": [test_recipient or "you"],
            },
        }

    # Custom list — validate and resolve names
    if filter_type == "custom":
        if not customer_ids:
            return {"error": "customer_ids required when filter_type is 'custom'"}
        customers = (await ctx.db.execute(
            select(Customer).where(
                Customer.id.in_(customer_ids),
                Customer.organization_id == ctx.org_id,
                Customer.is_active == True,
            )
        )).scalars().all()
        names = [c.display_name for c in customers]
        return {
            "action": "broadcast_email",
            "requires_confirmation": True,
            "preview": {
                "subject": subject,
                "body": body,
                "filter_type": "custom",
                "filter_label": f"{len(customers)} selected customer{'s' if len(customers) != 1 else ''}",
                "customer_ids": [c.id for c in customers],
                "customer_names": names,
                "recipient_count": len(customers),
            },
        }

    # Standard segment filters
    svc = BroadcastService(ctx.db)
    count = await svc.get_recipient_count(ctx.org_id, filter_type)

    filter_labels = {
        "all_active": "all active customers",
        "commercial": "commercial customers",
        "residential": "residential customers",
    }

    return {
        "action": "broadcast_email",
        "requires_confirmation": True,
        "preview": {
            "subject": subject,
            "body": body,
            "filter_type": filter_type,
            "filter_label": filter_labels.get(filter_type, filter_type),
            "recipient_count": count,
        },
    }


_EXECUTORS = {
    "chemical_dosing_calculator": _exec_dosing,
    "get_equipment": _exec_get_equipment,
    "find_replacement_parts": _exec_find_parts,
    "get_chemical_history": _exec_chemical_history,
    "get_service_history": _exec_service_history,
    "search_equipment_catalog": _exec_search_catalog,
    "get_customer_info": _exec_customer_info,
    "draft_broadcast_email": _exec_broadcast,
    "get_organization_info": _exec_org_info,
    # Phase 1 specific lookups
    "get_invoices": _exec_get_invoices,
    "get_estimates": _exec_get_estimates,
    "get_open_jobs": _exec_get_open_jobs,
    "get_cases": _exec_get_cases,
    "get_routes_today": _exec_get_routes_today,
    "get_techs": _exec_get_techs,
    "get_billing_terms": _exec_get_billing_terms,
    "get_service_tiers": _exec_get_service_tiers,
    "get_inspections": _exec_get_inspections,
    "get_payments": _exec_get_payments,
    # Phase 2 meta-tool
    "query_database": _exec_query_database,
}
