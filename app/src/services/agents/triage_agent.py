"""AI triage — quick check: does this email need a response?"""

import logging

logger = logging.getLogger(__name__)


async def ai_triage(body: str, subject: str, from_email: str) -> bool:
    """Quick AI check: does this email need a response from us?

    Returns True if we should respond, False if it's informational/gratitude/FYI.
    Uses Haiku for speed — ~200ms per call.
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
