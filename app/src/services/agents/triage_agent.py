"""AI triage — quick check: does this email need a response?"""

import logging

logger = logging.getLogger(__name__)


async def ai_triage(
    body: str,
    subject: str,
    from_email: str,
    *,
    organization_id: str | None = None,
) -> bool:
    """Quick AI check: does this email need a response from us?

    Returns True if we should respond, False if it's informational/gratitude/FYI.
    Uses Haiku for speed — ~200ms per call.

    DNA rule 2 — every AI agent learns. When `organization_id` is provided
    (orchestrator path), inject past `email_triage` corrections as lessons
    before the Claude call. Triage corrections land in `agent_corrections`
    whenever a human overrides the triage verdict (e.g., auto-handled mail
    later reopened for reply, or a no_response draft edited into a real
    reply). The lesson injection closes the pre-gen loop.

    Callers without org_id (eval harness, ad-hoc usage) still get triage —
    they just don't benefit from lesson injection.
    """
    if not body.strip():
        return False

    try:
        import anthropic
        from src.core.ai_models import get_model
        from src.core.config import get_settings
        settings = get_settings()
        if not settings.anthropic_api_key:
            return True  # Default to needing response if no AI

        lessons = ""
        if organization_id:
            try:
                from src.core.database import get_db_context
                from src.services.agent_learning_service import (
                    AGENT_EMAIL_TRIAGE,
                    AgentLearningService,
                )
                async with get_db_context() as learn_db:
                    learner = AgentLearningService(learn_db)
                    lessons = await learner.build_lessons_prompt(
                        organization_id, AGENT_EMAIL_TRIAGE,
                    ) or ""
            except Exception as e:  # noqa: BLE001
                logger.warning(f"ai_triage lesson injection failed (continuing without): {e}")

        model = await get_model("fast")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt = f"""You are triaging incoming emails for a pool service company.

From: {from_email}
Subject: {subject}
Body: {body[:500]}

Does this email require a response from us? Answer ONLY "yes" or "no".

Answer "no" if it's:
- A thank you, acknowledgment, or confirmation ("thanks", "got it", "sounds good")
- A status update that's just informational ("we expect to finish by May")
- An automated notification (order shipped, payment received)
- A marketing email or newsletter
- A forwarded message that's just FYI
- A one-word or very short affirmative ("ok", "yes", "perfect")

Answer "yes" if it's:
- Asking a question
- Requesting service, a quote, or scheduling
- Reporting a problem or complaint
- Asking for information we need to provide
- Requesting a callback or meeting"""
        if lessons:
            prompt = f"{lessons}\n\n{prompt}"

        response = await client.messages.create(
            model=model,
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip().lower()
        return answer.startswith("yes")

    except Exception as e:
        logger.warning(f"AI triage failed: {e}")
        return True  # Default to needing response on error
