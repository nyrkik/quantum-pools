"""DeepBlue eval runner — multi-turn execution + smart mode + seeding.

Runs eval prompts against Claude with real tool execution (reads) and mocked
writes (preview responses). Supports multi-turn conversations for compound
workflows. Tracks per-prompt pass history for smart mode.
"""

import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta

import anthropic
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model
from src.models.deepblue_eval_prompt import DeepBlueEvalPrompt
from src.services.deepblue.tools import TOOLS, ToolContext, execute_tool
from src.services.deepblue.engine import _build_system_prompt
from src.services.deepblue.context_builder import DeepBlueContext, build_context

logger = logging.getLogger(__name__)

SMART_MODE_THRESHOLD_PASSES = 5
SMART_MODE_STALE_DAYS = 7
MAX_EVAL_TURNS = 3


def _parse_json_list(val: str | None) -> list:
    if not val:
        return []
    try:
        result = json.loads(val)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def select_prompts_for_run(
    db: AsyncSession, org_id: str, mode: str = "full"
) -> list[DeepBlueEvalPrompt]:
    """Return prompts to run based on mode.

    - full: all active prompts
    - smart: skip prompts that have passed 5+ consecutively AND were run in the last 7 days
    """
    query = select(DeepBlueEvalPrompt).where(
        DeepBlueEvalPrompt.organization_id == org_id,
        DeepBlueEvalPrompt.active == True,
    ).order_by(DeepBlueEvalPrompt.created_at)

    all_prompts = (await db.execute(query)).scalars().all()

    if mode == "full":
        return list(all_prompts)

    # Smart mode: filter out stable prompts that were recently checked
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=SMART_MODE_STALE_DAYS)

    result = []
    for p in all_prompts:
        if p.consecutive_passes >= SMART_MODE_THRESHOLD_PASSES and p.last_run_at and p.last_run_at >= stale_cutoff:
            continue  # skip — stable and recent
        result.append(p)
    return result


async def run_single_prompt(
    prompt: DeepBlueEvalPrompt,
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    tool_ctx: ToolContext,
) -> dict:
    """Run a single prompt (possibly multi-turn) and evaluate against expectations.

    Returns a result dict with: prompt_key, prompt_text, tools_called, text_response, passed, reason.
    """
    messages = [{"role": "user", "content": prompt.prompt_text}]
    all_tools_called = []
    full_text = ""
    max_turns = max(1, min(prompt.max_turns, MAX_EVAL_TURNS))

    try:
        for turn in range(max_turns):
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )

            assistant_content = []
            turn_tool_uses = []

            for block in response.content:
                if block.type == "text":
                    full_text += block.text + "\n"
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    all_tools_called.append(block.name)
                    turn_tool_uses.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            if not turn_tool_uses:
                # No more tools to call — conversation is done
                break

            # Execute tools and feed results back
            tool_results_content = []
            for tc in turn_tool_uses:
                try:
                    result_str = await execute_tool(tc["name"], tc["input"], tool_ctx)
                except Exception as e:
                    result_str = json.dumps({"error": str(e)[:200]})
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_str,
                })
            messages.append({"role": "user", "content": tool_results_content})
    except Exception as e:
        return {
            "prompt_key": prompt.prompt_key,
            "prompt": prompt.prompt_text,
            "passed": False,
            "reason": f"Runner error: {str(e)[:200]}",
            "tools_called": all_tools_called,
            "text_response": full_text[:300],
        }

    # Evaluate
    passed, reason = _evaluate_result(prompt, all_tools_called, full_text)

    return {
        "prompt_key": prompt.prompt_key,
        "prompt": prompt.prompt_text,
        "tools_called": all_tools_called,
        "text_response": full_text[:300],
        "passed": passed,
        "reason": reason,
        "source": prompt.source,
        "max_turns": max_turns,
    }


def _evaluate_result(prompt: DeepBlueEvalPrompt, tools_called: list[str], text_response: str) -> tuple[bool, str]:
    """Check if the run matched expectations. Returns (passed, reason)."""
    expected_tools = _parse_json_list(prompt.expected_tools)
    expected_tools_any = _parse_json_list(prompt.expected_tools_any)
    must_not = _parse_json_list(prompt.must_not_contain)

    if prompt.expected_off_topic:
        if "focused on pool" not in text_response.lower() and "i'm here to help" not in text_response.lower():
            return False, "Did not decline off-topic request"
        return True, ""

    if prompt.expected_no_tools_required:
        if tools_called:
            return False, f"Called tools when none required: {tools_called}"
        return True, ""

    if expected_tools:
        missing = [t for t in expected_tools if t not in tools_called]
        if missing:
            return False, f"Missing expected tools: {missing}. Called: {tools_called}"

    if expected_tools_any:
        if not any(t in tools_called for t in expected_tools_any):
            return False, f"None of {expected_tools_any} were called. Got: {tools_called}"

    for phrase in must_not:
        if phrase.lower() in text_response.lower():
            return False, f"Response contained forbidden phrase: {phrase}"

    return True, ""


async def run_eval_suite(
    db: AsyncSession,
    org_id: str,
    client: anthropic.Anthropic,
    model: str,
    mode: str = "full",
) -> dict:
    """Run the full eval suite and update per-prompt pass history."""
    prompts = await select_prompts_for_run(db, org_id, mode)
    if not prompts:
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "results": [], "mode": mode}

    # Build context + system prompt once (same for all prompts)
    empty_ctx = DeepBlueContext()
    built = await build_context(db, org_id, empty_ctx)
    system_prompt = _build_system_prompt(built, "Evaluator")

    tool_ctx = ToolContext(db=db, org_id=org_id)

    results = []

    # Snapshot all prompt attributes into plain Python values before running.
    # Any subsequent DB errors won't cause lazy-load failures on the ORM objects.
    prompt_snapshots = []
    for p in prompts:
        prompt_snapshots.append({
            "id": p.id,
            "prompt_key": p.prompt_key,
            "prompt_text": p.prompt_text,
            "source": p.source,
            "max_turns": p.max_turns,
            "expected_tools": p.expected_tools,
            "expected_tools_any": p.expected_tools_any,
            "expected_off_topic": p.expected_off_topic,
            "expected_no_tools_required": p.expected_no_tools_required,
            "must_not_contain": p.must_not_contain,
        })

    # Commit to release any pending state from the seed step
    await db.commit()

    from sqlalchemy import update as _update

    for snap in prompt_snapshots:
        prompt_key = snap["prompt_key"]
        try:
            # Create a lightweight stand-in object for run_single_prompt's evaluator
            fake_prompt = type("P", (), snap)()
            result = await run_single_prompt(fake_prompt, client, model, system_prompt, tool_ctx)
        except Exception as e:
            logger.error(f"Eval runner error on {prompt_key}: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            result = {
                "prompt_key": prompt_key,
                "prompt": snap["prompt_text"],
                "passed": False,
                "reason": f"Runner exception: {str(e)[:200]}",
                "tools_called": [],
                "text_response": "",
            }
        results.append(result)

        # Update per-prompt stats in an isolated commit
        try:
            now = datetime.now(timezone.utc)
            if result["passed"]:
                await db.execute(
                    _update(DeepBlueEvalPrompt)
                    .where(DeepBlueEvalPrompt.id == snap["id"])
                    .values(
                        consecutive_passes=DeepBlueEvalPrompt.consecutive_passes + 1,
                        last_run_at=now,
                        last_passed_at=now,
                    )
                )
            else:
                await db.execute(
                    _update(DeepBlueEvalPrompt)
                    .where(DeepBlueEvalPrompt.id == snap["id"])
                    .values(
                        consecutive_passes=0,
                        last_run_at=now,
                    )
                )
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to update prompt stats for {prompt_key}: {e}")
            try:
                await db.rollback()
            except Exception:
                pass

    passed_count = sum(1 for r in results if r["passed"])

    # Count skipped in smart mode
    skipped = 0
    if mode == "smart":
        all_prompts = (await db.execute(
            select(DeepBlueEvalPrompt).where(
                DeepBlueEvalPrompt.organization_id == org_id,
                DeepBlueEvalPrompt.active == True,
            )
        )).scalars().all()
        skipped = len(list(all_prompts)) - len(prompts)

    return {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "skipped": skipped,
        "results": results,
        "mode": mode,
        "system_prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest()[:16],
        "model_used": model,
    }


async def seed_static_prompts(db: AsyncSession, org_id: str) -> int:
    """Seed the hardcoded EVAL_PROMPTS into the DB for this org. Idempotent."""
    from src.services.deepblue.eval_prompts import EVAL_PROMPTS

    existing = (await db.execute(
        select(DeepBlueEvalPrompt.prompt_key).where(
            DeepBlueEvalPrompt.organization_id == org_id,
            DeepBlueEvalPrompt.source == "static",
        )
    )).scalars().all()
    existing_keys = set(existing)

    added = 0
    for p in EVAL_PROMPTS:
        key = p["id"]
        if key in existing_keys:
            continue
        db.add(DeepBlueEvalPrompt(
            organization_id=org_id,
            prompt_key=key,
            prompt_text=p["prompt"],
            source="static",
            max_turns=p.get("max_turns", 1),
            expected_tools=json.dumps(p.get("expected_tools")) if p.get("expected_tools") else None,
            expected_tools_any=json.dumps(p.get("expected_tools_any")) if p.get("expected_tools_any") else None,
            expected_off_topic=bool(p.get("expected_off_topic")),
            expected_no_tools_required=bool(p.get("expected_no_tools_required")),
            must_not_contain=json.dumps(p.get("must_not_contain")) if p.get("must_not_contain") else None,
        ))
        added += 1

    if added > 0:
        await db.commit()
    return added
