"""AI-generated adversarial eval prompts.

Uses Sonnet (standard tier) to generate tricky test prompts based on:
- Existing tool list
- Recent eval failures
- Knowledge gaps (real user pain)
- The current prompt corpus (to avoid duplicates)

Returns drafts for human review — does NOT auto-activate them.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

import anthropic
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.models.deepblue_eval_prompt import DeepBlueEvalPrompt
from src.models.deepblue_eval_run import DeepBlueEvalRun
from src.models.deepblue_knowledge_gap import DeepBlueKnowledgeGap
from src.services.deepblue.tools import TOOLS

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


async def generate_adversarial_prompts(
    db: AsyncSession,
    org_id: str,
    count: int = 5,
    focus: str | None = None,
) -> list[dict]:
    """Generate adversarial eval prompt drafts using Sonnet. Returns list of dicts."""
    if not ANTHROPIC_KEY:
        return []

    # Gather context: existing prompts, recent failures, gaps
    existing = (await db.execute(
        select(DeepBlueEvalPrompt.prompt_text).where(
            DeepBlueEvalPrompt.organization_id == org_id,
            DeepBlueEvalPrompt.active == True,
        ).limit(50)
    )).scalars().all()

    # Recent failed prompts from last run
    last_run = (await db.execute(
        select(DeepBlueEvalRun).where(
            DeepBlueEvalRun.organization_id == org_id,
        ).order_by(desc(DeepBlueEvalRun.created_at)).limit(1)
    )).scalar_one_or_none()

    recent_failures = []
    if last_run and last_run.results_json:
        try:
            results = json.loads(last_run.results_json)
            recent_failures = [
                {"prompt": r["prompt"], "reason": r.get("reason", "")}
                for r in results if not r.get("passed")
            ][:10]
        except (json.JSONDecodeError, TypeError):
            pass

    # Recent unresolved knowledge gaps
    gaps = (await db.execute(
        select(DeepBlueKnowledgeGap).where(
            DeepBlueKnowledgeGap.organization_id == org_id,
            DeepBlueKnowledgeGap.promoted_to_eval == False,
        ).order_by(desc(DeepBlueKnowledgeGap.created_at)).limit(10)
    )).scalars().all()
    gap_questions = [g.user_question[:200] for g in gaps]

    # Tool list summary
    tool_summary = "\n".join(
        f"- {t['name']}: {t['description'][:100]}"
        for t in TOOLS
    )

    # Build the meta-prompt
    meta_prompt = f"""You are generating adversarial test prompts for DeepBlue, a pool service AI assistant.

AVAILABLE TOOLS:
{tool_summary}

EXISTING EVAL PROMPTS (do NOT duplicate these):
{chr(10).join(f'- "{p}"' for p in existing[:30])}

RECENT FAILURES (these patterns are tricky):
{chr(10).join(f'- "{f["prompt"]}" → {f["reason"][:100]}' for f in recent_failures[:5])}

REAL USER GAPS (questions DeepBlue has struggled with):
{chr(10).join(f'- "{q}"' for q in gap_questions[:5])}

{f"FOCUS AREA: {focus}" if focus else ""}

Generate {count} NEW adversarial test prompts. Each should:
1. Test something NOT already covered in existing prompts
2. Target a realistic pool service scenario
3. Be specific and actionable (not abstract)
4. Stress-test tool selection, chaining, or edge cases
5. Include typos, partial names, ambiguous references, or multi-step workflows when appropriate

Return ONLY a JSON array. Each entry:
{{
  "prompt": "the user's message text",
  "expected_tools_any": ["tool1", "tool2"],
  "max_turns": 1,
  "reasoning": "why this prompt is hard or valuable to test"
}}

Categories to consider:
- Multi-step workflows (find X, then do Y)
- Safety-critical dosing with edge values
- Ambiguous customer/property references
- Parts research with specific models
- Novel queries requiring query_database
- Off-topic refusals (but phrased to sneak past)
- Baseline context questions (should not trigger tools)

Return the JSON array only. No preamble, no markdown fences."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        model = await get_model("standard")
        response = client.messages.create(
            model=model,
            max_tokens=3000,
            messages=[{"role": "user", "content": meta_prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()

        # Strip markdown fences if any
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        drafts = json.loads(text)
        if not isinstance(drafts, list):
            return []

        # Validate each draft has required fields
        clean = []
        for d in drafts:
            if not isinstance(d, dict):
                continue
            prompt_text = str(d.get("prompt", "")).strip()
            if not prompt_text:
                continue
            clean.append({
                "prompt": prompt_text,
                "expected_tools_any": d.get("expected_tools_any", []) if isinstance(d.get("expected_tools_any"), list) else [],
                "max_turns": max(1, min(int(d.get("max_turns", 1)), 3)),
                "reasoning": str(d.get("reasoning", ""))[:500],
            })
        return clean[:count]
    except Exception as e:
        logger.error(f"Adversarial generation failed: {e}")
        return []
