"""DeepBlue Field engine — orchestrates Claude tool_use conversations."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.models.deepblue_conversation import DeepBlueConversation
from .context_builder import DeepBlueContext, build_context
from .tools import TOOLS, ToolContext, execute_tool

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MAX_TOOL_ROUNDS = 5  # Prevent infinite tool loops


def _extract_text_from_blocks(blocks) -> str:
    """Extract plain text from a list of Anthropic content blocks for display/summary."""
    if not isinstance(blocks, list):
        return str(blocks) if blocks else ""
    parts = []
    for b in blocks:
        if isinstance(b, dict):
            if b.get("type") == "text":
                parts.append(b.get("text", ""))
        elif hasattr(b, "type") and b.type == "text":
            parts.append(getattr(b, "text", ""))
    return " ".join(parts).strip()


def _build_system_prompt(ctx: DeepBlueContext, user_name: str, user_email: str | None = None) -> str:
    """Build the DeepBlue system prompt with resolved context."""
    user_line = f"You are talking to {user_name}"
    if user_email:
        user_line += f" ({user_email})"
    user_line += "."
    return f"""You are DeepBlue, the AI assistant for Sapphire Pool Service. You help with pool service operations, business management, and customer communications.

{user_line}

CURRENT CONTEXT (your organization profile and any relevant customer/property the user is viewing):
{ctx.context_summary}

The organization profile above is YOUR company's information. Use it directly when drafting communications that reference your own address, phone, or contact info — don't ask the user for it.

CAPABILITIES:
- Pool service: equipment troubleshooting, chemical dosing calculations, parts lookup, service history, inspections
- Business operations: draft emails, send broadcasts, customer lookups, invoices, estimates, jobs, cases, payments, routes, techs, billing terms, service tiers
- Field support: quick answers for techs on-site, equipment specs, code/inspection questions
- Database queries: for anything not covered by a specific tool, use query_database (SQL SELECT with safety limits)

TOOL SELECTION PRIORITY:
1. Use specific tools first (get_billing_documents, get_open_jobs, get_equipment, etc.) — they're fast and focused.
2. Use query_database ONLY as a last resort when no specific tool fits. This lets you answer novel questions about the data.
3. Never say "I don't have access to that" if it's data in the system. Try a specific tool first, then query_database.

CHEMICAL DOSING — SAFETY CRITICAL:
For ANY question involving pH, chlorine, alkalinity, calcium hardness, cyanuric acid, phosphates, or chemical amounts, you MUST call the chemical_dosing_calculator tool. This is non-negotiable.

- Do NOT calculate dosing amounts from your own knowledge, even if the math seems obvious.
- Do NOT respond with formulas like "add X oz of Y per 10k gallons" from memory.
- Do NOT estimate, approximate, or recommend amounts without calling the tool first.
- If the user asks "pH is 6.8 on a 45000 gallon pool, what do I add" — IMMEDIATELY call chemical_dosing_calculator with pool_gallons=45000, ph=6.8.
- If the user asks "how much chlorine should I add" — call the tool, never answer from knowledge.
- If pool volume isn't provided AND can't be looked up via get_equipment or the page context, ask the user for the volume — don't guess or use generic amounts.
- The tool has industry-standard formulas validated against real equipment. Your training data has generic approximations that can harm pools or swimmers. ALWAYS use the tool.

This rule applies regardless of whether the question feels simple. "What's low pH mean" is conceptual — answer from knowledge. "How much do I add" is dosing — use the tool.

MULTI-STEP WORKFLOWS (compound actions):
When the user asks for an action that requires a lookup first (e.g., "add equipment to the Walili pool" or "log a reading for Pinebrook"), chain the tool calls in a single turn when possible:
1. First tool call: find_property or find_customer to resolve IDs
2. Second tool call (same turn): the action tool (add_equipment_to_pool, log_chemical_reading, etc.)
Claude can call multiple tools per turn. Don't stop at the lookup — proceed directly to the action once you have the IDs.

PERSISTENCE (critical — don't give up easily):
When the user gives partial info (a name fragment, address piece, pool nickname, phone number), resolve it yourself. Try this order:
1. find_customer with the fragment (typo-tolerant — uses fuzzy matching)
2. find_property with the fragment (typo-tolerant)
3. search_equipment_catalog if it looks like an equipment term
4. query_database as a last resort
5. Only after all of these fail, ask the user — and ask specifically by showing your closest guesses ("I found 'Pinebrook Village' — is that who you mean?")

NOTE: find_customer and find_property are typo-tolerant. If "walili" returns nothing, the fuzzy fallback should catch "walali". You don't need to ask the user to check spelling.

NEVER ask the user for an ID (customer_id, property_id, bow_id). Always look IDs up yourself using the search tools.
NEVER ask "which one?" without first showing the options you found.

IMPORTANT — RETRY EVEN WHEN YOUR PRIOR TURNS SAID NO RESULTS:
If the user repeats a request, or you see in your own history that you previously said "no results" for a search, ALWAYS try the search tools again. The search tools may have been updated since the last attempt, and the user re-asking is a strong signal to try harder. Do not trust your own past "not found" statements — re-run the search with the current tools every time the user asks.

ERROR HANDLING:
When a tool returns an error, DO NOT quote the error text to the user. Errors contain internal debugging info like "database constraint", "validation failed", or "auto-scope missing" — these are for you, not the user.
- If a tool returns error + retry_hint, follow the hint and retry with a different approach.
- If the retry also fails, respond naturally with what you couldn't find — "I couldn't find a customer matching 'walili'. Can you give me another detail?" — not "I'm hitting a database constraint."

GUIDELINES:
- Be concise and practical. Field techs need quick answers, not essays.
- For chemical dosing, ALWAYS use the dosing calculator. Never estimate amounts yourself — chemical math is safety-critical.
- For equipment questions, look up the actual installed equipment first.
- When asked about parts, check the internal catalog first, then search online.
- For bulk communications, draft the email with the actual recipients and show a preview. The user decides whether to send a test first — don't force it.
- If you don't have enough context (no customer/property), ask the user to specify.
- Provide actionable answers: specific amounts, part numbers, steps to take.
- For safety-critical questions (gas heaters, electrical, chemical handling), include appropriate warnings.
- When presenting results from tool lookups, summarize them in natural language — don't dump raw data.
- You have deep pool industry knowledge. Use it for troubleshooting even without tools.
- You can also help with general business tasks: drafting communications, answering operational questions, planning.
- Keep responses under 200 words unless the user asks for detail or the answer requires it (like a dosing table).

ACTIONS AND CONFIRMATION — CRITICAL:
Tools that modify data (draft_broadcast_email, add_equipment_to_pool, log_chemical_reading, update_customer_note) return a preview response with "requires_confirmation": true. These tools DO NOT actually perform the action — they only produce a preview card that the user must explicitly confirm in the UI.

NEVER claim an action was completed based on a tool result with requires_confirmation: true. The correct response pattern after calling these tools:

WRONG: "Done! The email has been sent."
WRONG: "I've added the equipment to the pool."
WRONG: "Reading logged successfully."

RIGHT: "I've drafted the email. Click Confirm in the preview card above to send it."
RIGHT: "Ready to add the equipment. Review the preview and click Confirm to save."
RIGHT: "Reading ready to log. Please confirm to save it."

The preview card is rendered in the UI and contains the Confirm button. You must direct the user to click it. You have NO visibility into whether they clicked it — never assume they did.

SCOPE AND RELEVANCE:
- You are a pool service business assistant. Your purpose is to help with pool service operations, customer communications, and business tasks for this company.
- Politely decline clearly off-topic requests (creative writing, novels, homework help, recipes, travel planning, personal coding, etc.) with: "I'm focused on pool service operations. Is there something I can help with for your work?"
- Exception: casual greetings, small talk, and brief clarifications are fine. Don't be robotic.
- Exception: general business/operational questions (HR, accounting, scheduling, marketing for the pool business) are in scope.

LANGUAGE AND FORMATTING (important):
- NEVER expose internal identifiers, tool names, enum values, or field names to the user. Say "all active customers" not "all_active". Say "commercial customers only" not "commercial". Say "look up" not "get_customer_info". Say "check the database" not "query_database".
- When drafting emails: use plain text with proper paragraph spacing (blank line between paragraphs). No markdown asterisks or bold formatting unless the user explicitly asks. Emails should read naturally when rendered as plain text.
- When the user names specific customers or properties, look them up and resolve names to IDs BEFORE drafting a broadcast. Don't ask the user for IDs.
- For targeted broadcasts, draft with the actual recipients and use filter_type='custom' with the resolved customer_ids. Show the preview card — the user confirms or adjusts. Don't add extra test-send steps unless the user asks.
- If you can't do something, say it plainly in one sentence. Don't list workarounds as numbered options unless the user asked for alternatives.

EMAIL COPYWRITING STYLE (when drafting customer emails or broadcasts):
Write like a small business owner talking to a customer, not a corporate template generator. A pool service is personal — the customer likely knows the tech by name.

DO:
- Short sentences. Plain language. Direct tone.
- Get to the point in the first line. No throat-clearing.
- Use contractions ("we're", "don't", "you'll") — formal writing feels cold.
- If there's a single action for the customer, state it clearly and early.
- Sign off with just a name or "Sapphire Pool Service" — no taglines.

DO NOT (these are banned corporate-speak phrases):
- "Dear Valued Customer" — use "Hi [name]" if you have it, or skip the greeting for short notices
- "We hope this email finds you well" — ever
- "Please don't hesitate to contact us" — say "Questions? Email..." instead
- "Thank you for your continued business" — filler, cut it
- "Where blue meets brilliance" or any invented tagline — you don't have one, don't make one up
- "As always", "at your earliest convenience", "moving forward" — filler
- Signature blocks: do NOT include company name, email, website, or address in the draft body. End the draft with just a sign-off like "Thanks," or "Best," followed by a blank line. The system automatically appends the signature block (company name + contact info) to every outbound email. If you include one yourself, it duplicates.

BE ACCURATE:
- Don't say "we've moved" unless they actually moved. "We've updated" or "we want to remind you" is often more accurate.
- Don't invent details. If you don't know the old address, don't make one up. Ask the user.
- Match the facts the user gave you. Don't embellish.

LENGTH:
- Announcements and reminders: 3-5 short paragraphs max
- Apologies / complaint responses: even shorter, one clear acknowledgment + next step
- If the draft is longer than 150 words, cut something

REDRAFTS AND ITERATION:
If the conversation history contains a prior draft that violates these rules (e.g., uses "Dear Valued Customer", has an invented tagline, or uses corporate boilerplate), DO NOT iterate on that prior draft. REWRITE FROM SCRATCH applying the rules above. Your past drafts in history are not a template to preserve — they're examples of what NOT to do if they violated the rules. Every new draft request is a fresh start."""


class DeepBlueEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_message(
        self,
        org_id: str,
        user_id: str,
        user_name: str,
        message: str,
        context: DeepBlueContext,
        conversation_id: str | None = None,
        case_id: str | None = None,
        user_email: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Process a user message with streaming. Yields SSE event dicts.

        Event types:
        - {"type": "text_delta", "content": "..."}
        - {"type": "tool_call", "name": "...", "input": {...}}
        - {"type": "tool_result", "name": "...", "result": {...}}
        - {"type": "done", "conversation_id": "..."}
        - {"type": "error", "message": "..."}
        """
        if not ANTHROPIC_KEY:
            yield {"type": "error", "message": "AI service not configured"}
            return

        # Quota + rate limit check BEFORE anything else
        from .quota_service import check_quotas, record_usage, QuotaExceeded
        try:
            await check_quotas(self.db, org_id, user_id)
        except QuotaExceeded as e:
            yield {"type": "error", "message": str(e)}
            return

        start_time = datetime.now(timezone.utc)

        # Build rich context
        ctx = await build_context(self.db, org_id, context)
        system_prompt = _build_system_prompt(ctx, user_name, user_email)

        # Load or create conversation
        conversation = None
        messages_history = []
        if conversation_id:
            conversation = (await self.db.execute(
                select(DeepBlueConversation).where(
                    DeepBlueConversation.id == conversation_id,
                    DeepBlueConversation.user_id == user_id,
                )
            )).scalar_one_or_none()
            if conversation:
                messages_history = json.loads(conversation.messages_json or "[]")

        if not conversation:
            conversation = DeepBlueConversation(
                organization_id=org_id,
                user_id=user_id,
                context_json=json.dumps({
                    "customer_id": context.customer_id,
                    "property_id": context.property_id,
                    "bow_id": context.bow_id,
                    "visit_id": context.visit_id,
                }),
                title=message[:80],
                messages_json="[]",
                case_id=case_id,
            )
            self.db.add(conversation)
            await self.db.flush()

        # Append user message
        messages_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Build Claude messages — preserves text, tool_use, and tool_result blocks from prior turns
        # so Claude has full access to past tool results, not just text summaries.
        claude_messages = []
        for m in messages_history:
            if m.get("blocks"):
                # Structured turn with tool_use / tool_result blocks
                claude_messages.append({"role": m["role"], "content": m["blocks"]})
            else:
                # Plain text turn
                claude_messages.append({"role": m["role"], "content": m["content"]})

        tool_ctx = ToolContext(
            db=self.db,
            org_id=org_id,
            customer_id=context.customer_id,
            property_id=context.property_id,
            bow_id=context.bow_id,
            visit_id=context.visit_id,
        )

        total_input = 0
        total_output = 0
        meta_tool_invocations = []  # Track query_database calls for gap logging

        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        model = await get_model("fast")

        # Tool use loop — Claude may call tools, we execute and feed results back
        for _round in range(MAX_TOOL_ROUNDS):
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=system_prompt,
                tools=TOOLS,
                messages=claude_messages,
            )

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            # Process response content blocks
            assistant_content = []
            full_text = ""
            tool_calls_made = []

            for block in response.content:
                if block.type == "text":
                    full_text += block.text
                    assistant_content.append({"type": "text", "text": block.text})
                    yield {"type": "text_delta", "content": block.text}

                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    yield {"type": "tool_call", "name": tool_name, "input": tool_input}

                    # Execute tool
                    result_str = await execute_tool(tool_name, tool_input, tool_ctx)
                    result_data = json.loads(result_str)

                    # Track meta-tool invocations for gap logging
                    if tool_name == "query_database":
                        meta_tool_invocations.append({
                            "query": tool_input.get("query", ""),
                            "reason": tool_input.get("reason", ""),
                            "row_count": result_data.get("row_count"),
                        })

                    yield {"type": "tool_result", "name": tool_name, "result": result_data}

                    assistant_content.append({
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input,
                    })
                    tool_calls_made.append({
                        "tool_id": tool_id,
                        "name": tool_name,
                        "result": result_str,
                    })

            # Add assistant message to history
            claude_messages.append({"role": "assistant", "content": assistant_content})

            # If tools were called, add tool results and continue the loop
            if tool_calls_made:
                tool_results_content = []
                for tc in tool_calls_made:
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tc["tool_id"],
                        "content": tc["result"],
                    })
                claude_messages.append({"role": "user", "content": tool_results_content})
            else:
                # No tools called — we're done
                break

        # Save assistant response to conversation history.
        # We persist the full block structure from the tool loop so future turns
        # have access to past tool_use and tool_result data, not just text summaries.
        # claude_messages contains everything we sent/received this turn — but we only
        # want to append what was NEW this turn (everything after the initial messages_history).
        new_turn_blocks = claude_messages[len(messages_history):]  # skip the prior turns
        # The first entry in new_turn_blocks is the user message we just added; skip it
        # since it's already in messages_history.
        for i, msg in enumerate(new_turn_blocks):
            if i == 0 and msg.get("role") == "user" and isinstance(msg.get("content"), str):
                continue  # this is the current user message, already appended
            if isinstance(msg.get("content"), list):
                # Structured blocks — store in "blocks" field for reconstruction next turn
                messages_history.append({
                    "role": msg["role"],
                    "content": _extract_text_from_blocks(msg["content"]),
                    "blocks": msg["content"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                messages_history.append({
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        # Classify and log the turn
        from .category_tagger import classify_prompt, detect_off_topic_response
        from src.models.deepblue_message_log import DeepBlueMessageLog
        import hashlib

        category = classify_prompt(message)
        off_topic = detect_off_topic_response(full_text)
        if off_topic and category != "off_topic":
            category = "off_topic"

        tool_names = [tc["name"] for tc in tool_calls_made] if 'tool_calls_made' in dir() else []
        # Collect all tool names from the loop
        all_tools_called = []
        for hist_msg in claude_messages:
            if isinstance(hist_msg.get("content"), list):
                for block in hist_msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        all_tools_called.append(block.get("name", ""))

        latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        prompt_hash = hashlib.sha256(message.encode()).hexdigest()[:16]

        self.db.add(DeepBlueMessageLog(
            organization_id=org_id,
            user_id=user_id,
            conversation_id=conversation.id,
            message_index=len(messages_history) - 1,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            tool_calls_made=json.dumps(all_tools_called) if all_tools_called else None,
            tool_count=len(all_tools_called),
            user_prompt_hash=prompt_hash,
            user_prompt_length=len(message),
            response_length=len(full_text),
            latency_ms=latency_ms,
            category=category,
            off_topic_detected=off_topic,
            model_used="fast",
        ))

        # Record usage rollup
        await record_usage(
            db=self.db,
            org_id=org_id,
            user_id=user_id,
            input_tokens=total_input,
            output_tokens=total_output,
            tool_count=len(all_tools_called),
            off_topic=off_topic,
        )

        # Persist conversation
        conversation.messages_json = json.dumps(messages_history)
        conversation.total_input_tokens += total_input
        conversation.total_output_tokens += total_output
        conversation.updated_at = datetime.now(timezone.utc)

        # Auto-generate a smart title after the first exchange (user + assistant)
        if len(messages_history) == 2 and full_text:
            try:
                title_resp = client.messages.create(
                    model=model,
                    max_tokens=20,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Generate a short title (3-6 words, no quotes) for this conversation:\n"
                            f"User: {message[:200]}\n"
                            f"Assistant: {full_text[:200]}"
                        ),
                    }],
                )
                new_title = title_resp.content[0].text.strip().strip('"').strip("'")[:80]
                if new_title:
                    conversation.title = new_title
            except Exception:
                pass  # keep the default truncated title

        # Log knowledge gaps
        from src.models.deepblue_knowledge_gap import DeepBlueKnowledgeGap

        # Case 1: meta-tool was used → log each invocation
        for inv in meta_tool_invocations:
            self.db.add(DeepBlueKnowledgeGap(
                organization_id=org_id,
                user_id=user_id,
                conversation_id=conversation.id,
                user_question=message[:2000],
                resolution="meta_tool",
                sql_query=inv["query"][:5000],
                reason=inv["reason"][:500],
                result_row_count=inv["row_count"],
            ))

        # Case 2: unresolved — response contains "I don't know" type phrases
        if not meta_tool_invocations and full_text:
            unresolved_phrases = [
                "i don't have",
                "i can't find",
                "i don't know",
                "i'm not able to",
                "i cannot access",
                "i don't see",
                "i'm unable to",
                "no way to",
            ]
            lower_text = full_text.lower()
            if any(p in lower_text for p in unresolved_phrases):
                self.db.add(DeepBlueKnowledgeGap(
                    organization_id=org_id,
                    user_id=user_id,
                    conversation_id=conversation.id,
                    user_question=message[:2000],
                    resolution="unresolved",
                    reason=full_text[:500],
                ))

        await self.db.commit()

        yield {
            "type": "done",
            "conversation_id": conversation.id,
            "tokens": {"input": total_input, "output": total_output},
        }
