"""Matching emails to customers in the DB."""

import re
import logging

from sqlalchemy import select, desc, func
from src.core.database import get_db_context
from src.models.agent_message import AgentMessage
from src.models.agent_thread import AgentThread
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

        # 1. Direct email match (handles comma-separated email fields)
        result = await db.execute(
            select(Customer).where(
                Customer.is_active == True,
                func.lower(Customer.email).contains(from_email.lower()),
            ).limit(5)
        )
        email_matches = result.scalars().all()
        for c in email_matches:
            stored_emails = [e.strip().lower() for e in (c.email or "").split(",")]
            if from_email.lower() in stored_emails:
                customer = c
                match_method = "email"
                break

        # 1b. Check customer contacts (alternate emails)
        if not customer:
            from src.models.customer_contact import CustomerContact
            cc_result = await db.execute(
                select(CustomerContact).where(
                    func.lower(CustomerContact.email) == from_email.lower(),
                ).limit(1)
            )
            contact = cc_result.scalar_one_or_none()
            if contact:
                cust_result = await db.execute(
                    select(Customer).where(Customer.id == contact.customer_id, Customer.is_active == True)
                )
                customer = cust_result.scalar_one_or_none()
                if customer:
                    match_method = "contact_email"

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
        domain_single_match = None  # Hold single domain match — may be overridden by text search
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
                    # Don't commit yet — hold as fallback, let text search try first
                    domain_single_match = domain_matches[0]
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

        # 5. Search subject/body for customer display names and company names (scored)
        if not customer:
            subject_lower = subject.lower()
            body_lower = body[:1000].lower()
            result = await db.execute(
                select(Customer).where(Customer.is_active == True)
            )
            all_customers = result.scalars().all()
            candidates = []
            for c in all_customers:
                best_score = 0
                best_method = None
                # Check display_name (e.g. "Bridges at Woodcreek Oaks")
                display = c.display_name
                if display and len(display) >= 5:
                    dn_lower = display.lower()
                    if dn_lower in subject_lower:
                        score = len(display) * 3  # subject match worth 3x
                        if score > best_score:
                            best_score, best_method = score, "display_name_subject"
                    elif dn_lower in body_lower:
                        score = len(display) * 2
                        if score > best_score:
                            best_score, best_method = score, "display_name_body"
                # Check company_name (min 6 chars to avoid "BLVD", "PMI", "AIR" false positives)
                comp = c.company_name
                if comp and len(comp) >= 6:
                    cn_lower = comp.lower()
                    if cn_lower in subject_lower:
                        score = len(comp) * 3
                        if score > best_score:
                            best_score, best_method = score, "company_name_subject"
                    elif cn_lower in body_lower:
                        score = len(comp) * 2
                        if score > best_score:
                            best_score, best_method = score, "company_name_body"
                if best_score > 0:
                    candidates.append((best_score, best_method, c))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, method_detail, customer = candidates[0]
                match_method = method_detail

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

        # 7. Fall back to domain single match if nothing better was found
        if not customer and domain_single_match:
            customer = domain_single_match
            match_method = "domain"

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


async def verify_customer_match(org_id: str, from_email: str, thread_id: str):
    """Post-processing check: if sender should match a customer but didn't, auto-fix and alert admins."""
    try:
        from sqlalchemy import func
        from src.models.customer_contact import CustomerContact
        from src.models.notification import Notification
        from src.models.organization_user import OrganizationUser

        async with get_db_context() as db:
            thread = (await db.execute(
                select(AgentThread).where(AgentThread.id == thread_id)
            )).scalar_one_or_none()
            if not thread or thread.matched_customer_id:
                return

            # Check if this email exists in customers table
            cust = (await db.execute(
                select(Customer).where(
                    func.lower(Customer.email).contains(from_email.lower()),
                    Customer.is_active == True,
                )
            )).scalar_one_or_none()

            if not cust:
                contact = (await db.execute(
                    select(CustomerContact).where(
                        func.lower(CustomerContact.email) == from_email.lower(),
                    )
                )).scalar_one_or_none()
                if contact:
                    cust = (await db.execute(
                        select(Customer).where(Customer.id == contact.customer_id, Customer.is_active == True)
                    )).scalar_one_or_none()

            if not cust:
                return

            logger.warning(f"Customer match missed: {from_email} should be {cust.display_name} ({cust.id})")

            thread.matched_customer_id = cust.id
            thread.customer_name = cust.display_name

            latest_msg = (await db.execute(
                select(AgentMessage).where(
                    AgentMessage.thread_id == thread_id,
                    AgentMessage.direction == "inbound",
                ).order_by(desc(AgentMessage.received_at)).limit(1)
            )).scalar_one_or_none()
            if latest_msg and not latest_msg.matched_customer_id:
                latest_msg.matched_customer_id = cust.id
                latest_msg.customer_name = cust.display_name
                latest_msg.match_method = "post_verify"

            admins = (await db.execute(
                select(OrganizationUser).where(
                    OrganizationUser.organization_id == org_id,
                    OrganizationUser.role.in_(("owner", "admin")),
                )
            )).scalars().all()
            for ou in admins:
                db.add(Notification(
                    organization_id=org_id,
                    user_id=ou.user_id,
                    type="system_alert",
                    title=f"Customer match recovered: {cust.display_name}",
                    body=f"Email from {from_email} wasn't automatically matched. Auto-fixed.",
                    link="/inbox",
                ))

            await db.commit()

    except Exception as e:
        logger.error(f"Customer match verification failed: {e}")


async def save_discovered_contact(agent_msg_id: str):
    """When a message is confirmed (approved/sent), save the sender's email to the matched customer if missing."""
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentMessage).where(AgentMessage.id == agent_msg_id)
        )
        msg = result.scalar_one_or_none()
        if not msg or not msg.matched_customer_id:
            return

        cust_result = await db.execute(
            select(Customer).where(Customer.id == msg.matched_customer_id)
        )
        customer = cust_result.scalar_one_or_none()
        if not customer:
            return

        updated = False
        if not customer.email and msg.from_email:
            customer.email = msg.from_email
            updated = True
            logger.info(f"Saved email {msg.from_email} to customer {customer.display_name}")

        if customer.email and customer.email.lower() != msg.from_email.lower():
            if not msg.notes:
                msg.notes = ""
            if msg.from_email not in (msg.notes or ""):
                msg.notes = (msg.notes + f"\nAlternate email: {msg.from_email}").strip()
                updated = True

        if updated:
            await db.commit()
