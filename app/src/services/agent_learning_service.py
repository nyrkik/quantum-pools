"""Agent Learning Service — records corrections and retrieves relevant lessons for prompt injection.

Every AI agent calls `get_lessons()` before generating output, and the caller records
corrections via `record_correction()` when a human edits, rejects, or accepts the output.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.agent_correction import AgentCorrection

logger = logging.getLogger(__name__)

# Agent type constants
AGENT_EMAIL_CLASSIFIER = "email_classifier"
AGENT_EMAIL_DRAFTER = "email_drafter"
AGENT_DEEPBLUE = "deepblue_responder"
AGENT_COMMAND_EXECUTOR = "command_executor"
AGENT_JOB_EVALUATOR = "job_evaluator"
AGENT_ESTIMATE_GENERATOR = "estimate_generator"
AGENT_CUSTOMER_MATCHER = "customer_matcher"
AGENT_EQUIPMENT_RESOLVER = "equipment_resolver"


class AgentLearningService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_correction(
        self,
        org_id: str,
        agent_type: str,
        correction_type: str,
        original_output: str | None = None,
        corrected_output: str | None = None,
        input_context: str | None = None,
        category: str | None = None,
        customer_id: str | None = None,
        source_id: str | None = None,
        source_type: str | None = None,
    ) -> AgentCorrection:
        """Record a human correction to an AI output.

        correction_type: "edit" | "rejection" | "acceptance"
        """
        # Don't record acceptances with no useful signal
        if correction_type == "acceptance" and not category:
            return None

        # Truncate to keep storage reasonable
        correction = AgentCorrection(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            agent_type=agent_type,
            correction_type=correction_type,
            original_output=(original_output or "")[:2000] or None,
            corrected_output=(corrected_output or "")[:2000] or None,
            input_context=(input_context or "")[:1000] or None,
            category=category,
            customer_id=customer_id,
            source_id=source_id,
            source_type=source_type,
        )
        self.db.add(correction)
        await self.db.flush()
        return correction

    async def get_lessons(
        self,
        org_id: str,
        agent_type: str,
        category: str | None = None,
        customer_id: str | None = None,
        limit: int = 10,
    ) -> list[AgentCorrection]:
        """Retrieve the most relevant corrections for prompt injection.

        Priority:
        1. Same customer + same agent type (highest relevance)
        2. Same category + same agent type
        3. Same agent type (general lessons)

        Only corrections from last 90 days. Edits and rejections only (acceptances
        are low signal). Orders by recency.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        query = (
            select(AgentCorrection)
            .where(
                AgentCorrection.organization_id == org_id,
                AgentCorrection.agent_type == agent_type,
                AgentCorrection.correction_type.in_(["edit", "rejection"]),
                AgentCorrection.created_at >= cutoff,
            )
            .order_by(desc(AgentCorrection.created_at))
            .limit(limit * 3)  # fetch more, then prioritize
        )
        result = await self.db.execute(query)
        all_corrections = result.scalars().all()

        if not all_corrections:
            return []

        # Prioritize: customer-specific > category-specific > general
        customer_matches = []
        category_matches = []
        general = []

        for c in all_corrections:
            if customer_id and c.customer_id == customer_id:
                customer_matches.append(c)
            elif category and c.category == category:
                category_matches.append(c)
            else:
                general.append(c)

        # Interleave: customer first, then category, then general
        prioritized = customer_matches + category_matches + general
        selected = prioritized[:limit]

        # Update applied_count for tracking
        now = datetime.now(timezone.utc)
        for c in selected:
            c.applied_count = (c.applied_count or 0) + 1
            c.last_applied_at = now
        if selected:
            await self.db.flush()

        return selected

    async def build_lessons_prompt(
        self,
        org_id: str,
        agent_type: str,
        category: str | None = None,
        customer_id: str | None = None,
        limit: int = 8,
    ) -> str:
        """Build a prompt section with relevant past corrections.

        Returns empty string if no relevant corrections exist.
        Ready to inject directly into a system or user prompt.
        """
        lessons = await self.get_lessons(org_id, agent_type, category, customer_id, limit)
        if not lessons:
            return ""

        lines = ["LESSONS FROM PAST CORRECTIONS — apply these to your response:"]
        for c in lessons:
            if c.correction_type == "edit" and c.original_output and c.corrected_output:
                orig = c.original_output[:150]
                fixed = c.corrected_output[:150]
                lines.append(f"- You wrote: \"{orig}\" → Corrected to: \"{fixed}\"")
            elif c.correction_type == "rejection" and c.original_output:
                orig = c.original_output[:150]
                lines.append(f"- REJECTED: \"{orig}\" (your output was discarded)")

        return "\n".join(lines)
