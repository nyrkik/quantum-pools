"""Equipment change detection — analyzes completed jobs for equipment installs/replacements."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_message import AgentMessage
from src.models.property import Property
from src.models.water_feature import WaterFeature

logger = logging.getLogger(__name__)


async def detect_equipment_changes(db: AsyncSession, org_id: str, action: AgentAction):
    """When a job is marked done, use AI to detect if equipment was installed/replaced and update records."""
    customer_id = action.customer_id
    if not customer_id:
        return

    # Build job context — description + comments + email body
    job_text = action.description or ""
    comments = (await db.execute(
        select(AgentActionComment).where(AgentActionComment.action_id == action.id).order_by(AgentActionComment.created_at)
    )).scalars().all()
    for c in comments:
        if not c.text.startswith("[DRAFT_EMAIL]") and not c.text.startswith("[SENT_EMAIL]"):
            job_text += f"\n{c.text}"

    if action.agent_message_id:
        msg = (await db.execute(
            select(AgentMessage).where(AgentMessage.id == action.agent_message_id)
        )).scalar_one_or_none()
        if msg:
            job_text += f"\nEmail: {msg.body or ''}"
            if msg.final_response:
                job_text += f"\nOur reply: {msg.final_response}"

    if len(job_text.strip()) < 20:
        return

    # Get current equipment for context
    props = (await db.execute(
        select(Property).where(Property.customer_id == customer_id, Property.is_active == True)
    )).scalars().all()

    current_equip = []
    for p in props:
        wfs = (await db.execute(
            select(WaterFeature).where(WaterFeature.property_id == p.id, WaterFeature.is_active == True)
        )).scalars().all()
        for wf in wfs:
            from src.models.equipment_item import EquipmentItem
            items = (await db.execute(
                select(EquipmentItem).where(EquipmentItem.water_feature_id == wf.id, EquipmentItem.is_active == True)
            )).scalars().all()
            for ei in items:
                current_equip.append({
                    "id": ei.id,
                    "wf_id": wf.id,
                    "wf_name": wf.name or wf.water_type,
                    "type": ei.equipment_type,
                    "name": ei.normalized_name or f"{ei.brand or ''} {ei.model or ''}".strip(),
                })

    # Ask AI if equipment changed
    import anthropic
    import json
    from src.core.ai_models import get_model

    equip_list = "\n".join(f"- {e['type']}: {e['name']} (on {e['wf_name']})" for e in current_equip) if current_equip else "No equipment on file"

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=get_model("fast"),
            max_tokens=500,
            messages=[{"role": "user", "content": f"""Analyze this completed pool service job. Was any equipment installed, replaced, or removed?

JOB DETAILS:
{job_text[:1500]}

CURRENT EQUIPMENT ON FILE:
{equip_list}

If equipment was changed, return JSON:
{{"changes": [{{"action": "install"|"replace"|"remove", "equipment_type": "pump"|"filter"|"heater"|"chlorinator"|"automation"|"booster_pump"|"chemical_feeder", "old_name": "name of replaced item or null", "new_name": "full name of new equipment e.g. Waterway Crystal Water DE Filter", "new_brand": "manufacturer", "new_model": "model number if known"}}]}}

If NO equipment changes, return: {{"changes": []}}

JSON only, no markdown."""}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
    except Exception as e:
        logger.warning(f"AI equipment detection failed: {e}")
        return

    changes = result.get("changes", [])
    if not changes:
        return

    logger.info(f"Equipment changes detected for job {action.id}: {changes}")

    from src.models.equipment_item import EquipmentItem
    from src.services.parts.equipment_catalog_service import EquipmentCatalogService
    import uuid as _uuid

    catalog_svc = EquipmentCatalogService(db)

    for change in changes:
        eq_type = change.get("equipment_type", "equipment")
        new_name = change.get("new_name", "")
        action_type = change.get("action", "install")

        if action_type == "remove":
            old_name = change.get("old_name", "")
            if old_name:
                for e in current_equip:
                    if old_name.lower() in e["name"].lower() or e["name"].lower() in old_name.lower():
                        old_item = (await db.execute(
                            select(EquipmentItem).where(EquipmentItem.id == e["id"])
                        )).scalar_one_or_none()
                        if old_item:
                            old_item.is_active = False
            continue

        if not new_name:
            continue

        # Resolve new equipment against catalog
        catalog_result = await catalog_svc.resolve(new_name, eq_type)
        catalog_id = catalog_result.get("entry", {}).get("id") if catalog_result.get("entry") else None

        # Find which WF to add to
        target_wf_id = None
        old_name = change.get("old_name")
        if old_name and action_type == "replace":
            for e in current_equip:
                if e["type"] == eq_type and (old_name.lower() in e["name"].lower() or e["name"].lower() in old_name.lower()):
                    target_wf_id = e["wf_id"]
                    old_item = (await db.execute(
                        select(EquipmentItem).where(EquipmentItem.id == e["id"])
                    )).scalar_one_or_none()
                    if old_item:
                        old_item.is_active = False
                    break

        if not target_wf_id and props:
            first_wf = (await db.execute(
                select(WaterFeature).where(
                    WaterFeature.property_id == props[0].id, WaterFeature.is_active == True
                ).limit(1)
            )).scalar_one_or_none()
            if first_wf:
                target_wf_id = first_wf.id

        if not target_wf_id:
            continue

        new_item = EquipmentItem(
            id=str(_uuid.uuid4()),
            organization_id=org_id,
            water_feature_id=target_wf_id,
            equipment_type=eq_type,
            brand=change.get("new_brand"),
            model=change.get("new_model"),
            normalized_name=new_name,
            catalog_equipment_id=catalog_id,
        )
        db.add(new_item)
        logger.info(f"Added equipment: {new_name} ({eq_type}) to WF {target_wf_id}")

    await db.commit()
