"""Agent evaluation framework — tests agent outputs against expected results.

Supports:
1. Golden dataset evals — known input/output pairs
2. LLM-as-judge — grade agent output against criteria
3. Drift detection — compare metrics over time
4. Regression testing — run eval suite, report pass/fail

Usage:
    results = await run_eval_suite("classifier", org_id)
    # Returns: { passed: 8, failed: 2, total: 10, details: [...] }
"""

from src.core.ai_models import get_model
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, get_db_context

logger = logging.getLogger(__name__)


class AgentEvalCase(Base):
    """A test case for an agent — known input with expected output."""
    __tablename__ = "agent_eval_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_name: Mapped[str] = mapped_column(String(50), index=True)
    test_name: Mapped[str] = mapped_column(String(200))
    input_data: Mapped[str] = mapped_column(Text)  # JSON
    expected_output: Mapped[str | None] = mapped_column(Text)  # JSON or null for LLM-judge
    grading_criteria: Mapped[str | None] = mapped_column(Text)  # For LLM-as-judge: what to check
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source: Mapped[str | None] = mapped_column(String(50))  # "manual", "correction", "production"


class AgentEvalResult(Base):
    """Result of running an eval case."""
    __tablename__ = "agent_eval_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    eval_case_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_name: Mapped[str] = mapped_column(String(50), index=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    actual_output: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)  # 0.0 to 1.0
    judge_reasoning: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[str] = mapped_column(String(36), index=True)  # Groups results from same eval run
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


async def create_eval_from_correction(
    agent_name: str,
    input_data: dict,
    original_output: str,
    corrected_output: str,
):
    """Auto-create an eval case when a user corrects an agent's output.
    The corrected version becomes the expected output."""
    async with get_db_context() as db:
        case = AgentEvalCase(
            agent_name=agent_name,
            test_name=f"Correction: {input_data.get('subject', input_data.get('description', 'unknown'))[:100]}",
            input_data=json.dumps(input_data),
            expected_output=corrected_output,
            grading_criteria=f"Original draft was: {original_output[:200]}. User corrected to the expected output. The agent should produce something closer to the corrected version.",
            source="correction",
        )
        db.add(case)
        await db.commit()
        logger.info(f"Created eval case from correction for {agent_name}")


async def run_eval_suite(agent_name: str, organization_id: str = "") -> dict:
    """Run all active eval cases for an agent. Returns summary."""
    import anthropic
    import os
    from sqlalchemy import select

    run_id = str(uuid.uuid4())
    results = []

    async with get_db_context() as db:
        cases = (await db.execute(
            select(AgentEvalCase).where(
                AgentEvalCase.agent_name == agent_name,
                AgentEvalCase.is_active == True,
            )
        )).scalars().all()

    if not cases:
        return {"passed": 0, "failed": 0, "total": 0, "run_id": run_id, "details": []}

    for case in cases:
        try:
            from .observability import AgentTimer

            input_data = json.loads(case.input_data)

            # Run the agent function based on agent_name
            with AgentTimer() as timer:
                actual_output = await _run_agent(agent_name, input_data, organization_id)

            # Grade the result
            if case.expected_output:
                # Direct comparison or LLM-as-judge
                passed, score, reasoning = await _grade_output(
                    case.expected_output, actual_output,
                    case.grading_criteria, agent_name
                )
            else:
                # LLM-as-judge only
                passed, score, reasoning = await _grade_with_criteria(
                    actual_output, case.grading_criteria, agent_name
                )

            result = AgentEvalResult(
                eval_case_id=case.id,
                agent_name=agent_name,
                passed=passed,
                actual_output=str(actual_output)[:2000],
                score=score,
                judge_reasoning=reasoning,
                duration_ms=timer.duration_ms,
                run_id=run_id,
            )
            results.append({"test": case.test_name, "passed": passed, "score": score, "reasoning": reasoning})

            async with get_db_context() as db:
                db.add(result)
                await db.commit()

        except Exception as e:
            logger.error(f"Eval case {case.test_name} failed: {e}")
            results.append({"test": case.test_name, "passed": False, "score": 0, "reasoning": f"Error: {str(e)}"})

    passed = sum(1 for r in results if r["passed"])
    return {
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "run_id": run_id,
        "details": results,
    }


async def _run_agent(agent_name: str, input_data: dict, organization_id: str) -> str:
    """Run an agent with the given input and return its output as a string."""
    if agent_name == "classifier":
        from .classifier import classify_and_draft
        result = await classify_and_draft(
            from_email=input_data.get("from_email", "test@example.com"),
            subject=input_data.get("subject", ""),
            body=input_data.get("body", ""),
        )
        return json.dumps(result)

    elif agent_name == "customer_matcher":
        from .customer_matcher import match_customer
        result = await match_customer(
            from_email=input_data.get("from_email", ""),
            subject=input_data.get("subject", ""),
            body=input_data.get("body", ""),
        )
        return json.dumps(result) if result else "null"

    elif agent_name == "thread_manager":
        from .thread_manager import _normalize_subject
        return _normalize_subject(input_data.get("subject", ""))

    else:
        return f"No eval runner for agent: {agent_name}"


async def _grade_output(expected: str, actual: str, criteria: str | None, agent_name: str) -> tuple[bool, float, str]:
    """Grade agent output against expected output, optionally using LLM-as-judge."""
    import anthropic
    import os
    import re

    prompt = f"""Grade this AI agent's output against the expected output.

Agent: {agent_name}
Expected output: {expected[:500]}
Actual output: {actual[:500]}
{f'Additional criteria: {criteria}' if criteria else ''}

Respond with JSON:
{{"passed": true/false, "score": 0.0-1.0, "reasoning": "brief explanation"}}

Rules:
- passed=true if the actual output is functionally equivalent to expected (exact match not required)
- score: 1.0 = perfect match, 0.5 = partially correct, 0.0 = completely wrong
- For draft responses: judge on tone, content, and intent — not exact wording"""

    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model=await get_model("fast"),
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        json_match = re.search(r"\{.*\}", response.content[0].text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("passed", False), result.get("score", 0), result.get("reasoning", "")
    except Exception as e:
        return False, 0, f"Judge error: {str(e)}"

    return False, 0, "Failed to grade"


async def _grade_with_criteria(actual: str, criteria: str, agent_name: str) -> tuple[bool, float, str]:
    """Grade output using only criteria (no expected output)."""
    return await _grade_output("", actual, criteria, agent_name)


async def get_drift_report(agent_name: str, organization_id: str) -> dict:
    """Compare recent agent performance against historical baseline."""
    from .observability import get_agent_metrics

    current = await get_agent_metrics(organization_id, agent_name, hours=24)
    baseline = await get_agent_metrics(organization_id, agent_name, hours=168)  # 7 days

    drift = {}
    if baseline["total_calls"] > 0 and current["total_calls"] > 0:
        drift["success_rate_change"] = current["success_rate"] - baseline["success_rate"]
        if baseline["avg_duration_ms"] and current["avg_duration_ms"]:
            drift["duration_change_pct"] = round(
                (current["avg_duration_ms"] - baseline["avg_duration_ms"]) / baseline["avg_duration_ms"] * 100, 1
            )

    return {
        "agent": agent_name,
        "current_24h": current,
        "baseline_7d": baseline,
        "drift": drift,
        "alerts": _check_drift_alerts(drift),
    }


def _check_drift_alerts(drift: dict) -> list[str]:
    """Generate alerts from drift data."""
    alerts = []
    if drift.get("success_rate_change", 0) < -10:
        alerts.append(f"Success rate dropped {abs(drift['success_rate_change']):.1f}% vs 7-day baseline")
    if drift.get("duration_change_pct", 0) > 50:
        alerts.append(f"Response time increased {drift['duration_change_pct']:.0f}% vs 7-day baseline")
    return alerts
