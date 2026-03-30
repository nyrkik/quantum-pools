"""Matching emails to customers in the DB."""

import re
import logging

from sqlalchemy import select, desc, func
from src.core.database import get_db_context
from src.models.agent_message import AgentMessage
from src.models.customer import Customer
from src.models.property import Property
from src.models.water_feature import WaterFeature

logger = logging.getLogger(__name__)


def _extract_sender_name(from_header: str) -> str | None:
    """Extract the display name from a From header like 'John Smith <john@example.com>'."""
    # Try to get the name part before the email
    match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
    if match:
        name = match.group(1).strip()
        if name and "@" not in name:
            return name
    return None


async def match_customer(from_email: str, subject: str, body: str, from_header: str = "") -> dict | None:
    """Match an incoming email to a customer in the database. Returns context dict or None."""
    match_method = None

    async with get_db_context() as db:
        customer = None

        # 1. Direct email match
        result = await db.execute(
            select(Customer).where(
                func.lower(Customer.email) == from_email.lower(),
                Customer.is_active == True,
            ).limit(1)
        )
        customer = result.scalar_one_or_none()
        if customer:
            match_method = "email"

        # 2. Check previous messages — if we've matched this email before, reuse it
        if not customer:
            prev = await db.execute(
                select(AgentMessage).where(
                    AgentMessage.from_email == from_email,
                    AgentMessage.matched_customer_id.isnot(None),
                ).order_by(desc(AgentMessage.received_at)).limit(1)
            )
            prev_msg = prev.scalar_one_or_none()
            if prev_msg:
                cust_result = await db.execute(
                    select(Customer).where(Customer.id == prev_msg.matched_customer_id)
                )
                customer = cust_result.scalar_one_or_none()
                if customer:
                    match_method = "previous_match"

        # 3. Domain match (for property managers — same @company.com)
        multi_match_customers = None
        if not customer:
            domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
            if domain and domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "protonmail.com", "me.com"):
                result = await db.execute(
                    select(Customer).where(
                        Customer.email.ilike(f"%@{domain}"),
                        Customer.is_active == True,
                    ).limit(10)
                )
                domain_matches = result.scalars().all()
                if len(domain_matches) == 1:
                    customer = domain_matches[0]
                    match_method = "domain"
                elif len(domain_matches) > 1:
                    # Multiple customers with same domain — store for Claude to disambiguate
                    multi_match_customers = domain_matches
                    match_method = "domain_multi"

        # 4. Sender name match — extract name from "From: John Smith <john@example.com>"
        if not customer:
            sender_name = _extract_sender_name(from_header) if from_header else None
            if not sender_name:
                # Try extracting from email prefix: john.smith@... -> John Smith
                prefix = from_email.split("@")[0] if "@" in from_email else ""
                parts = re.split(r'[._-]', prefix)
                if len(parts) >= 2 and all(p.isalpha() for p in parts[:2]):
                    sender_name = " ".join(p.capitalize() for p in parts[:2])

            if sender_name:
                name_parts = sender_name.strip().split()
                if len(name_parts) >= 2:
                    first = name_parts[0]
                    last = name_parts[-1]
                    result = await db.execute(
                        select(Customer).where(
                            Customer.is_active == True,
                            func.lower(Customer.first_name) == first.lower(),
                            func.lower(Customer.last_name) == last.lower(),
                        ).limit(1)
                    )
                    customer = result.scalar_one_or_none()
                    if customer:
                        match_method = "sender_name"
                elif len(name_parts) == 1:
                    # Single name — try last name match (more unique than first)
                    result = await db.execute(
                        select(Customer).where(
                            Customer.is_active == True,
                            func.lower(Customer.last_name) == name_parts[0].lower(),
                        )
                    )
                    matches = result.scalars().all()
                    if len(matches) == 1:  # Only use if unambiguous
                        customer = matches[0]
                        match_method = "sender_name"

        # 5. Search subject/body for known company names
        if not customer:
            text_to_search = f"{subject} {body[:1000]}".lower()
            result = await db.execute(
                select(Customer).where(
                    Customer.is_active == True,
                    Customer.company_name.isnot(None),
                )
            )
            for c in result.scalars().all():
                if c.company_name and len(c.company_name) > 3 and c.company_name.lower() in text_to_search:
                    customer = c
                    match_method = "company_name"
                    break

        # 6. Search subject/body for customer last names (only if unique match)
        if not customer:
            text_to_search = f"{subject} {body[:1000]}".lower()
            result = await db.execute(
                select(Customer).where(Customer.is_active == True)
            )
            all_customers = result.scalars().all()
            name_matches = []
            for c in all_customers:
                if c.last_name and len(c.last_name) > 2 and c.last_name.lower() in text_to_search:
                    name_matches.append(c)
            if len(name_matches) == 1:  # Only use if unambiguous
                customer = name_matches[0]
                match_method = "body_name"

        if not customer and not multi_match_customers:
            return None

        # Multi-match: build context for all candidates, let Claude disambiguate
        if not customer and multi_match_customers:
            candidates = []
            for c in multi_match_customers:
                props_result = await db.execute(
                    select(Property).where(Property.customer_id == c.id, Property.is_active == True)
                )
                props = props_result.scalars().all()
                addresses = [p.full_address for p in props]
                candidates.append({
                    "customer_id": c.id,
                    "name": c.display_name,
                    "company": c.company_name,
                    "addresses": addresses,
                })
            return {
                "customer_id": None,
                "match_method": "domain_multi",
                "customer_name": None,
                "customer_type": multi_match_customers[0].customer_type,
                "company_name": multi_match_customers[0].company_name,
                "email": from_email,
                "phone": None,
                "preferred_day": None,
                "monthly_rate": None,
                "notes": None,
                "properties": [],
                "property_address": None,
                "_multi_candidates": candidates,
            }

        # Build context
        props_result = await db.execute(
            select(Property).where(
                Property.customer_id == customer.id,
                Property.is_active == True,
            )
        )
        properties = props_result.scalars().all()

        prop_contexts = []
        for prop in properties:
            wf_result = await db.execute(
                select(WaterFeature).where(
                    WaterFeature.property_id == prop.id,
                    WaterFeature.is_active == True,
                )
            )
            water_features = wf_result.scalars().all()

            from src.models.equipment_item import EquipmentItem
            from sqlalchemy.orm import selectinload

            wf_lines = []
            for wf in water_features:
                wf_parts = [f"{wf.name or wf.water_type}"]
                if wf.pool_gallons:
                    wf_parts.append(f"{wf.pool_gallons:,} gal")
                if wf.sanitizer_type:
                    wf_parts.append(f"sanitizer: {wf.sanitizer_type}")

                # Equipment from catalog
                equip_result = await db.execute(
                    select(EquipmentItem).options(selectinload(EquipmentItem.catalog_equipment)).where(
                        EquipmentItem.water_feature_id == wf.id,
                        EquipmentItem.is_active == True,
                    )
                )
                equip_items = equip_result.scalars().all()
                for ei in equip_items:
                    name = (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                            ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip())
                    if name:
                        wf_parts.append(f"{ei.equipment_type}: {name}")

                wf_lines.append(", ".join(wf_parts))

            p_parts = [prop.full_address]
            if prop.gate_code:
                p_parts.append(f"Gate: {prop.gate_code}")
            if prop.dog_on_property:
                p_parts.append("DOG on property")
            if prop.access_instructions:
                p_parts.append(f"Access: {prop.access_instructions}")
            if prop.notes:
                p_parts.append(f"Notes: {prop.notes}")

            prop_ctx = " | ".join(p_parts)
            if wf_lines:
                prop_ctx += "\n    Bodies of water: " + "; ".join(wf_lines)
            prop_contexts.append(prop_ctx)

        ctx = {
            "customer_id": customer.id,
            "match_method": match_method,
            "customer_name": customer.display_name,
            "customer_type": customer.customer_type,
            "company_name": customer.company_name,
            "email": customer.email,
            "phone": customer.phone,
            "preferred_day": customer.preferred_day,
            "monthly_rate": customer.monthly_rate,
            "notes": customer.notes,
            "properties": prop_contexts,
            "property_address": properties[0].full_address if properties else None,
        }
        return ctx
