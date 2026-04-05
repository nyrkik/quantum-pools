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


def _build_system_prompt(ctx: DeepBlueContext, user_name: str) -> str:
    """Build the DeepBlue system prompt with resolved context."""
    return f"""You are DeepBlue, the AI assistant for Sapphire Pool Service. You help with pool service operations, business management, and customer communications.

You are talking to {user_name}.

CURRENT CONTEXT (your organization profile and any relevant customer/property the user is viewing):
{ctx.context_summary}

The organization profile above is YOUR company's information. Use it directly when drafting communications that reference your own address, phone, or contact info — don't ask the user for it.

CAPABILITIES:
- Pool service: equipment troubleshooting, chemical dosing calculations, parts lookup, service history, inspections
- Business operations: draft emails, send broadcasts, customer lookups, invoices, estimates, jobs, cases, payments, routes, techs, billing terms, service tiers
- Field support: quick answers for techs on-site, equipment specs, code/inspection questions
- Database queries: for anything not covered by a specific tool, use query_database (SQL SELECT with safety limits)

TOOL SELECTION PRIORITY:
1. Use specific tools first (get_invoices, get_open_jobs, get_equipment, etc.) — they're fast and focused.
2. Use query_database ONLY as a last resort when no specific tool fits. This lets you answer novel questions about the data.
3. Never say "I don't have access to that" if it's data in the system. Try a specific tool first, then query_database.

GUIDELINES:
- Be concise and practical. Field techs need quick answers, not essays.
- For chemical dosing, ALWAYS use the chemical_dosing_calculator tool. Never estimate amounts yourself — chemical math is safety-critical.
- For equipment questions, look up the actual installed equipment first via get_equipment.
- When asked about parts, use find_replacement_parts with the specific model. It checks our catalog first, then searches online.
- For bulk communications, use draft_broadcast_email. Show the user a preview before sending.
- If you don't have enough context (no customer/property), ask the user to specify.
- Provide actionable answers: specific amounts, part numbers, steps to take.
- For safety-critical questions (gas heaters, electrical, chemical handling), include appropriate warnings.
- Format dosing results as a clean summary — don't dump raw JSON at the user.
- When presenting parts/equipment results, highlight the most relevant items first.
- You have deep pool industry knowledge. Use it for troubleshooting even without tools.
- You can also help with general business tasks: drafting communications, answering operational questions, planning.
- Keep responses under 200 words unless the user asks for detail or the answer requires it (like a dosing table)."""


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

        # Build rich context
        ctx = await build_context(self.db, org_id, context)
        system_prompt = _build_system_prompt(ctx, user_name)

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

        # Build Claude messages (strip our metadata fields)
        claude_messages = []
        for m in messages_history:
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

        # Save assistant response to conversation history
        messages_history.append({
            "role": "assistant",
            "content": full_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Persist conversation
        conversation.messages_json = json.dumps(messages_history)
        conversation.total_input_tokens += total_input
        conversation.total_output_tokens += total_output
        conversation.updated_at = datetime.now(timezone.utc)

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
