"""Email classification and draft response via Claude."""
from src.core.ai_models import get_model

import os
import re
import json
import logging

import anthropic
from sqlalchemy import select, desc
from src.core.database import get_db_context
from src.models.agent_message import AgentMessage

from .customer_matcher import match_customer

logger = logging.getLogger(__name__)

# Config from env
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FROM_EMAIL = os.environ.get("AGENT_FROM_EMAIL", "contact@sapphire-pools.com")
FROM_NAME = os.environ.get("AGENT_FROM_NAME", "Sapphire Pools")

DEFAULT_TONE_RULES = """CRITICAL TONE RULES — follow these exactly:
- NEVER admit fault, accept blame, or apologize for service failures. No "we apologize", "we're sorry", "that's not our standard", "we dropped the ball", etc.
- Keep responses neutral and fact-finding. Focus on gathering information and next steps, not explaining what went wrong.
- When a client complains, respond with concern but DO NOT validate their version of events. There are always two sides.
- Use phrases like "let me look into this", "I'd like to get some details", "let me check on your account", "we'll get back to you with an update"
- Never say "you're right" or "that shouldn't have happened" — instead redirect to resolution
- Be friendly and helpful, but protect the company's position at all times
- Address clients by first name if known, or "Hi" with their name. Use the contact name from the customer record when available.
- Don't use "family" as a suffix (e.g., "Blomquist family"). Just use their name.
- Don't over-promise urgency. "We'll look into this" or "we'll follow up" is fine — avoid "prioritizing", "right away", "ASAP" unless truly critical.
- NEVER include the property address or street address in the email body. The client knows where they live. Including it looks robotic and auto-generated. Reference the property by name only if it has one (e.g., "Pinebrook Village"), otherwise don't reference the location at all.
- NEVER include the customer's account number, invoice number, or internal reference IDs unless the customer specifically asked about them.
- Format draft_response as a proper email: greeting on its own line, body paragraphs separated by blank lines. Use \\n for line breaks in the JSON string.
- Do NOT include a signature block in the draft — the system appends it automatically. End with a brief closing like "Best," or "Thanks," on its own line."""


def _get_system_prompt():
    from_name = FROM_NAME or "Sapphire Pools"
    from_email = FROM_EMAIL or "contact@sapphire-pools.com"
    location = os.environ.get("AGENT_LOCATION", "Sacramento, CA")
    return """You are the AI assistant for """ + from_name + """, a commercial and residential pool service company in """ + location + """. You help manage client communications.

When classifying emails, respond with JSON:
{
  "category": "schedule|complaint|billing|gate_code|service_request|general|spam|auto_reply|no_response",
  "urgency": "low|medium|high",
  "confidence": "high|medium|low",
  "customer_name": "extracted name or null",
  "summary": "one line summary",
  "needs_approval": true/false,
  "draft_response": "the response to send or null if no_response",
  "internal_note": "note for the team if any",
  "actions": [
    {
      "action_type": "follow_up|bid|schedule_change|site_visit|callback|repair|equipment|invoice|other",
      "description": "short one-line summary, max 60 chars — action verb + what + identifier. For commercial: use property/business name (e.g., 'Install spa filter — Coventry Park'). For residential: use street address + last name (e.g., 'Diagnose pump leak — 4428 Walali Way (Lew)'). No emails or phone numbers.",
      "due_days": 1,
      "confidence": "high|medium|low"
    }
  ]
}

Guidelines:
- "confidence": how confident you are in your classification and response:
  - "high": clear intent, straightforward email, you're sure about the category and response. Examples: simple question with obvious answer, thank you, scheduling request with clear details.
  - "medium": reasonable interpretation but could be wrong, or email has some ambiguity. Examples: multi-topic email, unclear if they want a quote or just info, property reference but unsure which one.
  - "low": unclear intent, complex situation, multiple possible interpretations. Examples: forwarded chain with unclear context, legal/financial implications, complaint that could escalate.
- Each action also gets its own confidence: "high" = clearly needed, "medium" = probably needed but check, "low" = might not be needed
- category "auto_reply" means no-reply addresses, bounce notifications, marketing — ignore these
- category "spam" — junk, ignore
- category "no_response" — ONLY for truly empty acknowledgments with zero actionable content: "thank you", "thanks", "got it", "ok", "sounds good", "perfect", thumbs up, single-word replies. If the email contains ANY instructions, approvals, questions, requests, decisions, or new information — even brief ones — it is NOT no_response. When in doubt, classify as "general" with needs_approval=true. A short reply like "go ahead" or "you can replace it" IS actionable and needs a response.
- needs_approval = false ONLY for: gate code confirmations where no action needed
- needs_approval = true for: schedule changes, complaints, billing questions, service requests, anything requiring a decision or a real reply
- Draft responses should be warm, professional, concise. Sign as the company team, not a specific person.
- Never promise specific dates/times without approval
- If the email mentions a property name you recognize, include it in the response
- Keep responses under 3 sentences unless the situation requires more

CRITICAL TONE RULES — follow these exactly:
- NEVER admit fault, accept blame, or apologize for service failures. No "we apologize", "we're sorry", "that's not our standard", "we dropped the ball", etc.
- Keep responses neutral and fact-finding. Focus on gathering information and next steps, not explaining what went wrong.
- When a client complains, respond with concern but DO NOT validate their version of events. There are always two sides.
- Use phrases like "let me look into this", "I'd like to get some details", "let me check on your account", "we'll get back to you with an update"
- Never say "you're right" or "that shouldn't have happened" — instead redirect to resolution
- Be friendly and helpful, but protect the company's position at all times
- Address clients by first name if known, or "Hi" with their name. Use the contact name from the customer record when available.
- Don't use "family" as a suffix (e.g., "Blomquist family"). Just use their name.
- Don't over-promise urgency. "We'll look into this" or "we'll follow up" is fine — avoid "prioritizing", "right away", "ASAP" unless truly critical.
- NEVER include the property address or street address in the email body. The client knows where they live. Including it looks robotic and auto-generated. Reference the property by name only if it has one (e.g., "Pinebrook Village"), otherwise don't reference the location at all.
- NEVER include the customer's account number, invoice number, or internal reference IDs unless the customer specifically asked about them.
- Format draft_response as a proper email: greeting on its own line, body paragraphs separated by blank lines. Use \\n for line breaks in the JSON string.
- Do NOT include a signature block in the draft — the system appends it automatically. End with a brief closing like "Best," or "Thanks," on its own line.
- "actions" array: extract follow-up work the team needs to do. MAXIMUM 2 actions per email. ONE action per distinct task — do NOT split a single task into steps or create separate actions for related follow-ups. For example, "inspect pool and report back" is ONE action, not two. "Get termination details and clarify timeline" is ONE action, not five. When in doubt, combine into fewer actions. Include due_days (business days). Leave empty [] if no action needed.
- Common action types: "bid" (send a quote/proposal), "follow_up" (check back with client), "schedule_change" (modify service day/frequency), "site_visit" (go inspect/assess), "callback" (phone call needed), "repair" (fix equipment/issue), "equipment" (order/replace equipment)
- Action descriptions should be specific — include property name, client name, part numbers, and any details from the email. "Replace filter" is too vague. "Replace spa filter — Coventry Park (Overton)" is good."""


SYSTEM_PROMPT = _get_system_prompt()


async def get_correction_history(from_email: str, category: str | None) -> list[dict]:
    """Get past corrections (edited drafts) to learn from. Returns most relevant examples."""
    async with get_db_context() as db:
        # Get messages where draft was edited before sending (final != draft)
        query = (
            select(AgentMessage)
            .where(
                AgentMessage.status == "sent",
                AgentMessage.draft_response.isnot(None),
                AgentMessage.final_response.isnot(None),
                AgentMessage.draft_response != AgentMessage.final_response,
            )
            .order_by(desc(AgentMessage.sent_at))
            .limit(20)
        )
        result = await db.execute(query)
        edited = result.scalars().all()

        # Also get rejections to learn what NOT to do
        reject_query = (
            select(AgentMessage)
            .where(AgentMessage.status == "rejected")
            .order_by(desc(AgentMessage.approved_at))
            .limit(5)
        )
        reject_result = await db.execute(reject_query)
        rejected = reject_result.scalars().all()

        # Also get recent successful sends for same email (conversation continuity)
        convo_query = (
            select(AgentMessage)
            .where(
                AgentMessage.from_email == from_email,
                AgentMessage.status.in_(("sent", "auto_sent")),
            )
            .order_by(desc(AgentMessage.sent_at))
            .limit(5)
        )
        convo_result = await db.execute(convo_query)
        past_convos = convo_result.scalars().all()

        corrections = []

        # Prioritize: same-email corrections, then same-category, then general
        for msg in edited:
            relevance = "general"
            if msg.from_email == from_email:
                relevance = "same_client"
            elif msg.category == category:
                relevance = "same_category"
            corrections.append({
                "type": "correction",
                "relevance": relevance,
                "category": msg.category,
                "subject": msg.subject,
                "original_draft": msg.draft_response[:200],
                "corrected_to": msg.final_response[:200],
            })

        # Sort: same_client first, then same_category, then general
        priority = {"same_client": 0, "same_category": 1, "general": 2}
        corrections.sort(key=lambda x: priority.get(x["relevance"], 3))

        for msg in rejected:
            corrections.append({
                "type": "rejection",
                "category": msg.category,
                "subject": msg.subject,
                "rejected_draft": msg.draft_response[:200] if msg.draft_response else "",
                "reason": "Team decided not to respond",
            })

        past_exchanges = []
        for msg in past_convos:
            past_exchanges.append({
                "subject": msg.subject,
                "received": msg.received_at.isoformat() if msg.received_at else None,
                "response": msg.final_response[:200] if msg.final_response else msg.draft_response[:200] if msg.draft_response else "",
            })

        return {
            "corrections": corrections[:8],  # Cap at 8 most relevant
            "past_exchanges": past_exchanges,
        }


def build_context_prompt(customer_ctx: dict | None, history: dict | None) -> str:
    """Build the context section to inject into the system prompt."""
    parts = []

    if customer_ctx and customer_ctx.get("_multi_candidates"):
        candidates = customer_ctx["_multi_candidates"]
        parts.append("=== MULTIPLE POSSIBLE CUSTOMERS ===")
        parts.append(f"The sender's email domain matches {len(candidates)} customers. Determine which one based on the email content:")
        for i, c in enumerate(candidates, 1):
            addrs = ", ".join(c["addresses"][:3]) if c["addresses"] else "no properties"
            parts.append(f"  {i}. {c['name']}{' (' + c['company'] + ')' if c.get('company') else ''} — {addrs}")
        parts.append("")
        parts.append("In your JSON response, set customer_name to the matched customer's name. If you cannot determine which customer, set customer_name to null and add an internal_note explaining the ambiguity.")

    elif customer_ctx:
        parts.append("=== KNOWN CUSTOMER ===")
        parts.append(f"Name: {customer_ctx['customer_name']}")
        parts.append(f"Type: {customer_ctx['customer_type']}")
        if customer_ctx.get("company_name"):
            parts.append(f"Company: {customer_ctx['company_name']}")
        if customer_ctx.get("phone"):
            parts.append(f"Phone: {customer_ctx['phone']}")
        if customer_ctx.get("preferred_day"):
            parts.append(f"Service days: {customer_ctx['preferred_day']}")
        if customer_ctx.get("monthly_rate"):
            parts.append(f"Rate: ${customer_ctx['monthly_rate']:.2f}/mo")
        if customer_ctx.get("notes"):
            parts.append(f"Customer notes: {customer_ctx['notes']}")
        for i, prop in enumerate(customer_ctx.get("properties", [])):
            parts.append(f"Property {i+1}: {prop}")
        parts.append("")
        parts.append("Use the customer's name and reference their property details when relevant. This is a known client — respond with familiarity, not as a cold contact.")

    if history:
        exchanges = history.get("past_exchanges", [])
        if exchanges:
            parts.append("")
            parts.append("=== RECENT CONVERSATION HISTORY ===")
            for ex in exchanges[:3]:
                parts.append(f"- [{ex.get('received', '?')}] Re: {ex['subject']}")
                parts.append(f"  Our reply: {ex['response']}")
            parts.append("")
            parts.append("Continue the existing relationship tone. Reference prior communication if relevant.")

        corrections = history.get("corrections", [])
        if corrections:
            parts.append("")
            parts.append("=== LEARN FROM PAST CORRECTIONS ===")
            parts.append("The team has previously edited drafts. Adapt your style based on these:")
            for c in corrections[:5]:
                if c["type"] == "correction":
                    parts.append(f"- [{c.get('category', '?')}] Draft: \"{c['original_draft']}\"")
                    parts.append(f"  Corrected to: \"{c['corrected_to']}\"")
                elif c["type"] == "rejection":
                    parts.append(f"- [{c.get('category', '?')}] REJECTED draft for: {c['subject']}")
                    parts.append(f"  Draft was: \"{c.get('rejected_draft', '')}\"")
            parts.append("")
            parts.append("Match the corrected tone and style. Avoid patterns from rejected drafts.")

    return "\n".join(parts) if parts else ""


async def classify_and_draft(from_email: str, subject: str, body: str, from_header: str = "") -> dict:
    """Use Claude to classify the email and draft a response with customer context and learning."""
    # Build context from database
    customer_ctx = await match_customer(from_email, subject, body, from_header)
    history = await get_correction_history(from_email, None)

    context_block = build_context_prompt(customer_ctx, history)

    full_system = SYSTEM_PROMPT
    if context_block:
        full_system += "\n\n" + context_block

    # Inject lessons from past corrections
    try:
        async with get_db_context() as learn_db:
            from src.services.agent_learning_service import AgentLearningService, AGENT_EMAIL_CLASSIFIER
            learner = AgentLearningService(learn_db)
            org_id = customer_ctx.get("organization_id") if customer_ctx else None
            customer_id = customer_ctx.get("customer_id") if customer_ctx else None
            category = customer_ctx.get("category") if customer_ctx else None
            if org_id:
                lessons = await learner.build_lessons_prompt(
                    org_id, AGENT_EMAIL_CLASSIFIER,
                    category=category, customer_id=customer_id,
                )
                if lessons:
                    full_system += "\n\n" + lessons
                await learn_db.commit()
    except Exception:
        pass  # learning is non-critical

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    user_msg = f"From: {from_email}\nSubject: {subject}\n\n{body[:2000]}"

    from .observability import AgentTimer, log_agent_call
    with AgentTimer() as timer:
        response = client.messages.create(
            model=await get_model("fast"),
            max_tokens=500,
            system=full_system,
            messages=[{"role": "user", "content": user_msg}],
        )

    text = response.content[0].text
    usage = response.usage

    # Parse JSON from response
    try:
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            # Enrich with matched customer data
            if customer_ctx:
                # Handle multi-match: Claude picks the customer by name
                if customer_ctx.get("_multi_candidates") and result.get("customer_name"):
                    picked_name = result["customer_name"].lower()
                    for c in customer_ctx["_multi_candidates"]:
                        if c["name"].lower() in picked_name or picked_name in c["name"].lower():
                            result["_matched_customer_id"] = c["customer_id"]
                            result["_match_method"] = "domain_multi"
                            # Get property address
                            if c.get("addresses"):
                                result["_property_address"] = c["addresses"][0]
                            break
                    if not result.get("_matched_customer_id"):
                        result["_match_method"] = "domain_multi_unresolved"
                elif customer_ctx.get("customer_id"):
                    if not result.get("customer_name"):
                        result["customer_name"] = customer_ctx["customer_name"]
                    result["_matched_customer_id"] = customer_ctx["customer_id"]
                    result["_match_method"] = customer_ctx["match_method"]
                    result["_property_address"] = customer_ctx.get("property_address")
            return result
            # Log successful classification
            import asyncio
            asyncio.ensure_future(log_agent_call(
                organization_id="",  # Set by orchestrator
                agent_name="classifier",
                action="classify_and_draft",
                input_summary=f"{from_email}: {subject}",
                output_summary=f"category={result.get('category')}, needs_approval={result.get('needs_approval')}",
                success=True,
                model=await get_model("fast"),
                input_tokens=getattr(usage, 'input_tokens', None),
                output_tokens=getattr(usage, 'output_tokens', None),
                duration_ms=timer.duration_ms,
            ))
            return result
    except json.JSONDecodeError:
        pass

    result = {
        "category": "general",
        "urgency": "medium",
        "customer_name": customer_ctx["customer_name"] if customer_ctx else None,
        "summary": subject,
        "needs_approval": True,
        "draft_response": "Thank you for reaching out. We'll get back to you shortly.",
        "internal_note": "Failed to parse AI response",
    }
    if customer_ctx:
        result["_matched_customer_id"] = customer_ctx["customer_id"]
        result["_match_method"] = customer_ctx["match_method"]
        result["_property_address"] = customer_ctx.get("property_address")
    return result
