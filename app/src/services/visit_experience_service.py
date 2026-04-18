"""Visit Experience service — full visit lifecycle for tech field work."""

import os
import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from src.presenters.visit_presenter import VisitPresenter

from src.models.visit import Visit, VisitStatus
from src.models.visit_photo import VisitPhoto
from src.models.visit_checklist_entry import VisitChecklistEntry
from src.models.service_checklist_item import ServiceChecklistItem
from src.models.chemical_reading import ChemicalReading
from src.models.property import Property
from src.models.customer import Customer
from src.models.water_feature import WaterFeature
from src.models.tech import Tech
from src.models.route import RouteStop
from src.core.config import get_settings
from src.core.exceptions import NotFoundError


ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10MB


class VisitExperienceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Start visit
    # ------------------------------------------------------------------

    async def start_visit(
        self,
        org_id: str,
        property_id: str,
        tech_user_id: str,
        route_stop_id: Optional[str] = None,
    ) -> dict:
        """Create a new in-progress visit with full context."""
        # Resolve tech from user_id
        tech = await self._get_tech_for_user(org_id, tech_user_id)

        # Get property + customer_id
        prop = await self._get_property(org_id, property_id)

        now = datetime.now(timezone.utc)
        visit = Visit(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            property_id=property_id,
            customer_id=prop.customer_id,
            tech_id=tech.id,
            scheduled_date=now.date(),
            status=VisitStatus.in_progress.value,
            started_at=now,
            actual_arrival=now,
            route_stop_id=route_stop_id,
        )
        self.db.add(visit)
        await self.db.flush()

        # Create checklist entries from org's active items
        await self._create_checklist_entries(org_id, visit.id)

        await self.db.flush()
        return await self.get_context(org_id, visit.id)

    # ------------------------------------------------------------------
    # Context — single-call fetch
    # ------------------------------------------------------------------

    async def get_context(self, org_id: str, visit_id: str) -> dict:
        """Fetch everything needed for the visit page in one call."""
        visit = await self._get_visit(org_id, visit_id)
        prop = await self._get_property(org_id, visit.property_id)

        # Customer
        cust_result = await self.db.execute(
            select(Customer).where(Customer.id == prop.customer_id)
        )
        customer = cust_result.scalar_one_or_none()

        # Water features
        wf_result = await self.db.execute(
            select(WaterFeature).where(
                WaterFeature.property_id == prop.id,
                WaterFeature.organization_id == org_id,
            ).order_by(WaterFeature.water_type, WaterFeature.name)
        )
        water_features = wf_result.scalars().all()

        # Checklist entries
        cl_result = await self.db.execute(
            select(VisitChecklistEntry).where(
                VisitChecklistEntry.visit_id == visit_id
            ).order_by(VisitChecklistEntry.name)
        )
        checklist = cl_result.scalars().all()

        # Readings from this visit
        rd_result = await self.db.execute(
            select(ChemicalReading).where(
                ChemicalReading.visit_id == visit_id,
                ChemicalReading.organization_id == org_id,
            ).order_by(ChemicalReading.created_at.desc())
        )
        readings = rd_result.scalars().all()

        # Last readings per water feature (most recent before this visit)
        last_readings = {}
        for wf in water_features:
            lr_result = await self.db.execute(
                select(ChemicalReading).where(
                    ChemicalReading.organization_id == org_id,
                    ChemicalReading.property_id == prop.id,
                    ChemicalReading.water_feature_id == wf.id,
                    ChemicalReading.visit_id != visit_id,
                ).order_by(ChemicalReading.created_at.desc()).limit(1)
            )
            last = lr_result.scalar_one_or_none()
            if last:
                last_readings[wf.id] = _reading_to_dict(last)

        # Photos
        ph_result = await self.db.execute(
            select(VisitPhoto).where(
                VisitPhoto.visit_id == visit_id,
                VisitPhoto.organization_id == org_id,
            ).order_by(VisitPhoto.created_at.desc())
        )
        photos = ph_result.scalars().all()

        # Charges
        charges = await self._get_visit_charges(org_id, visit_id)

        # Elapsed
        elapsed = 0
        if visit.started_at:
            elapsed = int((datetime.now(timezone.utc) - visit.started_at).total_seconds())

        return {
            "visit": {
                "id": visit.id,
                "status": visit.status,
                "started_at": visit.started_at.isoformat() if visit.started_at else None,
                "actual_arrival": visit.actual_arrival.isoformat() if visit.actual_arrival else None,
                "actual_departure": visit.actual_departure.isoformat() if visit.actual_departure else None,
                "duration_minutes": visit.duration_minutes,
                "notes": visit.notes,
                "service_performed": visit.service_performed,
                "route_stop_id": visit.route_stop_id,
                "tech_id": visit.tech_id,
                "scheduled_date": visit.scheduled_date.isoformat() if visit.scheduled_date else None,
            },
            "customer": {
                "id": customer.id,
                "name": customer.full_name,
                "company": customer.company_name,
                "phone": customer.phone,
                "email": customer.email,
            } if customer else None,
            "property": {
                "id": prop.id,
                "name": prop.name,
                "address": prop.full_address,
                "city": prop.city,
                "gate_code": prop.gate_code,
                "access_instructions": prop.access_instructions,
                "dog_on_property": prop.dog_on_property,
            },
            "water_features": await VisitPresenter(self.db).water_features(water_features),
            "checklist": [
                {
                    "id": entry.id,
                    "name": entry.name,
                    "checklist_item_id": entry.checklist_item_id,
                    "completed": entry.completed,
                    "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
                    "notes": entry.notes,
                }
                for entry in checklist
            ],
            "readings": [_reading_to_dict(r) for r in readings],
            "last_readings": last_readings,
            "photos": [
                {
                    "id": p.id,
                    "photo_url": p.photo_url,
                    "category": p.category,
                    "caption": p.caption,
                    "water_feature_id": p.water_feature_id,
                    "created_at": p.created_at.isoformat(),
                }
                for p in photos
            ],
            "charges": charges,
            "elapsed_seconds": elapsed,
        }

    # ------------------------------------------------------------------
    # Active visit
    # ------------------------------------------------------------------

    async def get_active_visit(self, org_id: str, tech_user_id: str) -> Optional[dict]:
        """Find in-progress visit for this tech. At most one."""
        tech = await self._get_tech_for_user(org_id, tech_user_id)
        result = await self.db.execute(
            select(Visit).where(
                Visit.organization_id == org_id,
                Visit.tech_id == tech.id,
                Visit.status == VisitStatus.in_progress.value,
            ).order_by(Visit.started_at.desc()).limit(1)
        )
        visit = result.scalar_one_or_none()
        if not visit:
            return None
        return await self.get_context(org_id, visit.id)

    # ------------------------------------------------------------------
    # Checklist
    # ------------------------------------------------------------------

    async def update_checklist(
        self, org_id: str, visit_id: str, entries: list[dict]
    ) -> list[dict]:
        """Bulk update checklist entries: [{id, completed, notes}]."""
        visit = await self._get_visit(org_id, visit_id)
        now = datetime.now(timezone.utc)

        for entry_data in entries:
            entry_id = entry_data.get("id")
            if not entry_id:
                continue
            result = await self.db.execute(
                select(VisitChecklistEntry).where(
                    VisitChecklistEntry.id == entry_id,
                    VisitChecklistEntry.visit_id == visit.id,
                )
            )
            entry = result.scalar_one_or_none()
            if not entry:
                continue

            if "completed" in entry_data:
                was_completed = entry.completed
                entry.completed = entry_data["completed"]
                if entry_data["completed"] and not was_completed:
                    entry.completed_at = now
                elif not entry_data["completed"]:
                    entry.completed_at = None
            if "notes" in entry_data:
                entry.notes = entry_data["notes"]

        await self.db.flush()

        # Return updated list
        cl_result = await self.db.execute(
            select(VisitChecklistEntry).where(
                VisitChecklistEntry.visit_id == visit.id
            ).order_by(VisitChecklistEntry.name)
        )
        return [
            {
                "id": e.id,
                "name": e.name,
                "checklist_item_id": e.checklist_item_id,
                "completed": e.completed,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "notes": e.notes,
            }
            for e in cl_result.scalars().all()
        ]

    # ------------------------------------------------------------------
    # Chemical readings
    # ------------------------------------------------------------------

    async def add_reading(
        self,
        org_id: str,
        visit_id: str,
        water_feature_id: Optional[str],
        readings: dict,
    ) -> dict:
        """Create chemical reading for this visit + water feature."""
        visit = await self._get_visit(org_id, visit_id)

        # Map frontend field names to model field names
        field_map = {"cya": "cyanuric_acid", "fc": "free_chlorine", "tc": "total_chlorine",
                     "alk": "alkalinity", "ch": "calcium_hardness", "temp": "water_temp"}
        mapped = {field_map.get(k, k): v for k, v in readings.items() if v is not None}

        reading = ChemicalReading(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            property_id=visit.property_id,
            visit_id=visit.id,
            water_feature_id=water_feature_id,
            **mapped,
        )

        # Auto-recommendations via ChemicalService
        from src.services.chemical_service import ChemicalService
        pool_gallons = None
        if water_feature_id:
            wf_result = await self.db.execute(
                select(WaterFeature).where(WaterFeature.id == water_feature_id)
            )
            wf = wf_result.scalar_one_or_none()
            if wf:
                pool_gallons = wf.pool_gallons
        if pool_gallons is None:
            prop_result = await self.db.execute(
                select(Property).where(Property.id == visit.property_id)
            )
            p = prop_result.scalar_one_or_none()
            if p:
                pool_gallons = p.pool_gallons

        reading.recommendations = ChemicalService.generate_recommendations(reading, pool_gallons)

        self.db.add(reading)
        await self.db.flush()

        # Instrumentation — source="visit" attributes the reading to the
        # tech-completed visit workflow (distinct from manual /readings
        # POST or deepblue chat). Actor is system here because the service
        # method doesn't take a caller context; the visit itself identifies
        # the tech via visit.assigned_to.
        from src.services.events.chemistry import (
            emit_chemical_reading_logged,
            emit_chemistry_out_of_range_events,
        )
        await emit_chemical_reading_logged(self.db, reading, source="visit")
        await emit_chemistry_out_of_range_events(self.db, reading)

        await self.db.refresh(reading)
        return _reading_to_dict(reading)

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------

    async def upload_photo(
        self,
        org_id: str,
        visit_id: str,
        file_bytes: bytes,
        filename: str,
        category: Optional[str] = None,
        water_feature_id: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> dict:
        """Save photo to disk, create VisitPhoto record."""
        visit = await self._get_visit(org_id, visit_id)

        settings = get_settings()
        upload_dir = os.path.join(settings.upload_dir, "visits", visit.id)
        os.makedirs(upload_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1] or ".jpg"
        safe_filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(upload_dir, safe_filename)
        with open(filepath, "wb") as f:
            f.write(file_bytes)

        photo_url = f"/uploads/visits/{visit.id}/{safe_filename}"
        photo = VisitPhoto(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            visit_id=visit.id,
            water_feature_id=water_feature_id,
            photo_url=photo_url,
            category=category,
            caption=caption,
        )
        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)

        return {
            "id": photo.id,
            "photo_url": photo.photo_url,
            "category": photo.category,
            "caption": photo.caption,
            "water_feature_id": photo.water_feature_id,
            "created_at": photo.created_at.isoformat(),
        }

    async def delete_photo(self, org_id: str, visit_id: str, photo_id: str) -> bool:
        """Delete a visit photo record and file."""
        visit = await self._get_visit(org_id, visit_id)
        result = await self.db.execute(
            select(VisitPhoto).where(
                VisitPhoto.id == photo_id,
                VisitPhoto.visit_id == visit.id,
                VisitPhoto.organization_id == org_id,
            )
        )
        photo = result.scalar_one_or_none()
        if not photo:
            raise NotFoundError("Photo not found")

        # Delete file from disk
        settings = get_settings()
        if photo.photo_url.startswith("/uploads/"):
            filepath = os.path.join(settings.upload_dir, photo.photo_url.replace("/uploads/", "", 1))
            if os.path.exists(filepath):
                os.remove(filepath)

        await self.db.delete(photo)
        await self.db.flush()
        return True

    # ------------------------------------------------------------------
    # Complete visit
    # ------------------------------------------------------------------

    async def complete_visit(
        self, org_id: str, visit_id: str, notes: Optional[str] = None
    ) -> dict:
        """Complete the visit, calculate duration, mark route stop."""
        visit = await self._get_visit(org_id, visit_id)

        if visit.status == VisitStatus.completed.value:
            raise ValueError("Visit already completed")

        now = datetime.now(timezone.utc)
        visit.status = VisitStatus.completed.value
        visit.actual_departure = now

        # Calculate duration
        if visit.started_at:
            delta = now - visit.started_at
            visit.duration_minutes = int(delta.total_seconds() / 60)

        if notes is not None:
            visit.notes = notes

        # Mark route stop as completed (no status column — use visit link)
        # RouteStop doesn't have a status field, so the visit completion
        # is tracked via the visit's status + route_stop_id link.

        await self.db.flush()

        # Activation funnel — first-visit-completed for this org.
        from src.services.events.activation_tracker import emit_if_first
        await emit_if_first(
            self.db,
            "activation.first_visit_completed",
            organization_id=org_id,
            entity_refs={"visit_id": visit.id, "property_id": visit.property_id},
            source="visit_experience",
        )

        await self.db.refresh(visit)

        return {
            "visit_id": visit.id,
            "status": visit.status,
            "duration_minutes": visit.duration_minutes,
            "started_at": visit.started_at.isoformat() if visit.started_at else None,
            "completed_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # Auto-close stale visits
    # ------------------------------------------------------------------

    async def auto_close_stale_visits(self, org_id: str) -> int:
        """Auto-complete visits that have been in_progress for over 8 hours.

        Safety net: no visit should remain open indefinitely. Called periodically
        by the agent poller (every ~30 minutes).
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=8)
        result = await self.db.execute(
            select(Visit).where(
                Visit.organization_id == org_id,
                Visit.status == VisitStatus.in_progress.value,
                Visit.started_at < cutoff,
            )
        )
        stale_visits = result.scalars().all()

        now = datetime.now(timezone.utc)
        for visit in stale_visits:
            visit.status = VisitStatus.completed.value
            visit.actual_departure = now
            if visit.started_at:
                visit.duration_minutes = int((now - visit.started_at).total_seconds() / 60)
            existing_notes = visit.notes or ""
            auto_note = "Auto-completed at end of day"
            if existing_notes:
                visit.notes = f"{existing_notes}\n{auto_note}"
            else:
                visit.notes = auto_note

        if stale_visits:
            await self.db.flush()

        return len(stale_visits)

    # ------------------------------------------------------------------
    # _build_wf_context REMOVED — use VisitPresenter.water_features() instead

    # ------------------------------------------------------------------

    async def get_property_history(
        self, org_id: str, property_id: str, limit: int = 10
    ) -> list[dict]:
        """Visit history for a property with summary info."""
        result = await self.db.execute(
            select(Visit, Tech).outerjoin(Tech, Visit.tech_id == Tech.id).where(
                Visit.organization_id == org_id,
                Visit.property_id == property_id,
            ).order_by(Visit.scheduled_date.desc(), Visit.created_at.desc()).limit(limit)
        )

        history = []
        for visit, tech in result.all():
            # Count photos
            photo_count_result = await self.db.execute(
                select(func.count(VisitPhoto.id)).where(VisitPhoto.visit_id == visit.id)
            )
            photo_count = photo_count_result.scalar() or 0

            # Count readings
            reading_count_result = await self.db.execute(
                select(func.count(ChemicalReading.id)).where(
                    ChemicalReading.visit_id == visit.id
                )
            )
            reading_count = reading_count_result.scalar() or 0

            # Checklist completion
            checklist_result = await self.db.execute(
                select(
                    func.count(VisitChecklistEntry.id),
                    func.count(VisitChecklistEntry.id).filter(VisitChecklistEntry.completed == True),
                ).where(VisitChecklistEntry.visit_id == visit.id)
            )
            total_items, completed_items = checklist_result.one()

            history.append({
                "id": visit.id,
                "scheduled_date": visit.scheduled_date.isoformat() if visit.scheduled_date else None,
                "status": visit.status,
                "duration_minutes": visit.duration_minutes,
                "tech_name": tech.full_name if tech else None,
                "notes": visit.notes,
                "photo_count": photo_count,
                "reading_count": reading_count,
                "checklist_total": total_items or 0,
                "checklist_completed": completed_items or 0,
            })

        return history

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_visit(self, org_id: str, visit_id: str) -> Visit:
        result = await self.db.execute(
            select(Visit).where(Visit.id == visit_id, Visit.organization_id == org_id)
        )
        visit = result.scalar_one_or_none()
        if not visit:
            raise NotFoundError("Visit not found")
        return visit

    async def _get_property(self, org_id: str, property_id: str) -> Property:
        result = await self.db.execute(
            select(Property).where(
                Property.id == property_id, Property.organization_id == org_id
            )
        )
        prop = result.scalar_one_or_none()
        if not prop:
            raise NotFoundError("Property not found")
        return prop

    async def _get_tech_for_user(self, org_id: str, user_id: str) -> Tech:
        result = await self.db.execute(
            select(Tech).where(
                Tech.organization_id == org_id,
                Tech.user_id == user_id,
                Tech.is_active == True,
            )
        )
        tech = result.scalar_one_or_none()
        if not tech:
            raise NotFoundError("No active tech profile found for this user")
        return tech

    async def _create_checklist_entries(self, org_id: str, visit_id: str) -> None:
        """Create checklist entries from org's active checklist items."""
        result = await self.db.execute(
            select(ServiceChecklistItem).where(
                ServiceChecklistItem.organization_id == org_id,
                ServiceChecklistItem.is_active == True,
                ServiceChecklistItem.is_default == True,
            ).order_by(ServiceChecklistItem.sort_order, ServiceChecklistItem.name)
        )
        items = result.scalars().all()
        for item in items:
            entry = VisitChecklistEntry(
                id=str(uuid.uuid4()),
                visit_id=visit_id,
                checklist_item_id=item.id,
                name=item.name,
                completed=False,
            )
            self.db.add(entry)

    async def _get_visit_charges(self, org_id: str, visit_id: str) -> list[dict]:
        """Get charges linked to this visit."""
        try:
            from src.models.visit_charge import VisitCharge
            result = await self.db.execute(
                select(VisitCharge).where(
                    VisitCharge.organization_id == org_id,
                    VisitCharge.visit_id == visit_id,
                ).order_by(VisitCharge.created_at.desc())
            )
            charges = result.scalars().all()
            return [
                {
                    "id": c.id,
                    "description": c.description,
                    "amount": c.amount,
                    "status": c.status,
                    "category": c.category,
                }
                for c in charges
            ]
        except Exception:
            return []


def _reading_to_dict(r: ChemicalReading) -> dict:
    return {
        "id": r.id,
        "water_feature_id": r.water_feature_id,
        "ph": r.ph,
        "free_chlorine": r.free_chlorine,
        "total_chlorine": r.total_chlorine,
        "combined_chlorine": r.combined_chlorine,
        "alkalinity": r.alkalinity,
        "calcium_hardness": r.calcium_hardness,
        "cyanuric_acid": r.cyanuric_acid,
        "tds": r.tds,
        "phosphates": r.phosphates,
        "salt": r.salt,
        "water_temp": r.water_temp,
        "recommendations": r.recommendations,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
