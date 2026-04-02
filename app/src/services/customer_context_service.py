"""Customer context builder — builds rich context strings for AI prompts."""

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.agent_message import AgentMessage
from src.models.customer import Customer
from src.models.property import Property
from src.models.water_feature import WaterFeature


async def build_customer_context(db: AsyncSession, org_id: str, customer_id: str | None = None, customer_name: str | None = None, agent_message_id: str | None = None, property_address: str | None = None) -> tuple[str | None, str]:
    """Build customer context string for AI calls. Returns (customer_id, context_text)."""
    customer_context = ""

    if property_address:
        customer_context += f"\nJob address: {property_address}"
    if customer_name:
        customer_context += f"\nJob contact: {customer_name}"

    # Try to find customer from linked message
    if not customer_id and agent_message_id:
        msg_check = await db.execute(
            select(AgentMessage).where(
                AgentMessage.id == agent_message_id,
                AgentMessage.organization_id == org_id,
            )
        )
        parent_msg = msg_check.scalar_one_or_none()
        if parent_msg and parent_msg.matched_customer_id:
            customer_id = parent_msg.matched_customer_id

    # For standalone actions, find customer by name
    if not customer_id and customer_name:
        cust_match = await db.execute(
            select(Customer).where(
                Customer.organization_id == org_id,
                Customer.is_active == True,
                or_(
                    Customer.display_name_col.ilike(f"%{customer_name}%"),
                    Customer.first_name.ilike(f"%{customer_name}%"),
                    Customer.last_name.ilike(f"%{customer_name}%"),
                    Customer.company_name.ilike(f"%{customer_name}%"),
                )
            ).limit(1)
        )
        matched = cust_match.scalar_one_or_none()
        if matched:
            customer_id = matched.id

    if customer_id:
        cust = (await db.execute(
            select(Customer).where(Customer.id == customer_id)
        )).scalar_one_or_none()
        if cust:
            customer_context += f"\nCustomer: {cust.display_name}"
            if cust.email:
                customer_context += f"\nEmail: {cust.email}"
            if cust.phone:
                customer_context += f"\nPhone: {cust.phone}"
            if cust.preferred_day:
                customer_context += f"\nService days: {cust.preferred_day}"
            if cust.monthly_rate:
                customer_context += f"\nRate: ${cust.monthly_rate:.2f}/mo"

            props = (await db.execute(
                select(Property).where(
                    Property.customer_id == customer_id,
                    Property.is_active == True,
                )
            )).scalars().all()
            for p in props:
                customer_context += f"\nProperty: {p.full_address}"
                if p.gate_code:
                    customer_context += f" (Gate: {p.gate_code})"
                if p.access_instructions:
                    customer_context += f" Access: {p.access_instructions}"
                if p.dog_on_property:
                    customer_context += " DOG"
                wfs = (await db.execute(
                    select(WaterFeature).where(
                        WaterFeature.property_id == p.id,
                        WaterFeature.is_active == True,
                    )
                )).scalars().all()
                for wf in wfs:
                    parts = [wf.name or wf.water_type]
                    if wf.pool_gallons:
                        parts.append(f"{wf.pool_gallons:,} gal")
                    customer_context += f"\n  {', '.join(parts)}"

                    from src.models.equipment_item import EquipmentItem
                    equip_result = await db.execute(
                        select(EquipmentItem).options(selectinload(EquipmentItem.catalog_equipment)).where(
                            EquipmentItem.water_feature_id == wf.id,
                            EquipmentItem.is_active == True,
                        )
                    )
                    for ei in equip_result.scalars().all():
                        name = (ei.catalog_equipment.canonical_name if ei.catalog_equipment else
                                ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip())
                        if name:
                            customer_context += f"\n    {ei.equipment_type}: {name}"

    return customer_id, customer_context
