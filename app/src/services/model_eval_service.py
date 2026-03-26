"""Model evaluation and auto-promotion service.

Tests a candidate AI model against real-world test cases and auto-promotes
if it passes the threshold. Notifications go to all admin+ users.

Usage:
    svc = ModelEvalService(db)
    result = await svc.evaluate_candidate("fast", "claude-haiku-5-20260101")
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.ai_models import get_model, set_model
from src.models.notification import Notification
from src.models.organization_user import OrganizationUser, OrgRole
from src.services.agents.observability import log_agent_call, AgentTimer

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_EVAL_TIMEOUT = 30  # seconds per test case


# ---------------------------------------------------------------------------
# Test case data
# ---------------------------------------------------------------------------

CLASSIFIER_TESTS = [
    {"input": "what's the gate code?", "expected": {"intent": "question"}, "check": "exact_field", "critical": True},
    {"input": "draft email to send", "expected": {"intent": "command", "sub_intent": "draft_email"}, "check": "exact_field", "critical": True},
    {"input": "installed the new pump", "expected": {"intent": "status_update"}, "check": "exact_field", "critical": False},
    {"input": "all done, job complete", "expected": {"intent": "completion"}, "check": "exact_field", "critical": True},
    {"input": "FYI meeting moved to 3pm", "expected": {"intent": "info_only"}, "check": "exact_field", "critical": False},
    {"input": "assign to Shane", "expected": {"intent": "command", "sub_intent": "assign"}, "check": "exact_field", "critical": True},
    {"input": "mark as done", "expected": {"intent": "command", "sub_intent": "mark_done"}, "check": "exact_field", "critical": True},
    {"input": "create estimate for the repair", "expected": {"intent": "command", "sub_intent": "create_estimate"}, "check": "exact_field", "critical": False},
    {"input": "notify kim about this", "expected": {"intent": "command", "sub_intent": "notify"}, "check": "exact_field", "critical": False},
    {"input": "replaced filter, draft email to let them know", "expected": {"intent": "command", "sub_intent": "draft_email"}, "check": "exact_field", "critical": True},
    {"input": "pump is overheating, thermal protection kicking in", "expected": {"intent": "status_update"}, "check": "exact_field", "critical": False},
    {"input": "do we service this property?", "expected": {"intent": "question"}, "check": "exact_field", "critical": False},
    {"input": "schedule for Thursday", "expected": {"intent": "command", "sub_intent": "schedule"}, "check": "exact_field", "critical": False},
    {"input": "here's the diagnosis from today's visit", "expected": {"intent": "status_update"}, "check": "exact_field", "critical": False},
]

EMAIL_DRAFT_TESTS = [
    {"instruction": "remind customer about upcoming filter replacement", "check": "json_valid", "critical": False},
    {"instruction": "follow up on pump repair diagnosis", "check": "json_valid", "critical": False},
    {"instruction": "send estimate for equipment replacement", "check": "json_valid", "critical": False},
]

RESOLUTION_TESTS = [
    {"comment": "all done, filter installed", "job_desc": "Install new filter", "expected_resolved": True, "check": "exact_field", "critical": False},
    {"comment": "visited but parts on backorder", "job_desc": "Replace pump motor", "expected_resolved": False, "check": "exact_field", "critical": False},
    {"comment": "completed the repair, everything working", "job_desc": "Fix leaking valve", "expected_resolved": True, "check": "exact_field", "critical": False},
    {"comment": "need to come back next week with parts", "job_desc": "Equipment repair", "expected_resolved": False, "check": "exact_field", "critical": False},
]

# Aggregate by agent
TEST_SUITE: dict[str, list[dict]] = {
    "classifier": CLASSIFIER_TESTS,
    "email_drafter": EMAIL_DRAFT_TESTS,
    "resolution_evaluator": RESOLUTION_TESTS,
}

# Thresholds
OVERALL_PASS_THRESHOLD = 0.85
CLASSIFIER_PASS_THRESHOLD = 0.90


# ---------------------------------------------------------------------------
# Prompt templates (mirrors production agents, for isolated candidate testing)
# ---------------------------------------------------------------------------

_CLASSIFIER_PROMPT = """Classify this comment on a pool service job into exactly one intent.

Job context:
Type: equipment
Description: General pool service task
Status: open
Assigned to: unassigned

Comment by Tech: "{comment}"

Intents:
- question: asking for information ("what's the gate code?", "do we have their email?", "need the address")
- command: requesting an action ("draft email to let them know", "create estimate", "assign to Shane", "schedule for Thursday", "notify the customer", "mark as done", "send email")
- status_update: reporting progress ("visited today, pump is overheating", "installed the filter", "parts on order")
- completion: explicitly marking work done ("completed", "all done", "finished the repair", "job's done")
- info_only: general note, no action needed ("FYI the gate code changed", "spoke with manager")

For MIXED comments (e.g. "installed filter, draft email to let them know"):
Pick the MOST ACTIONABLE: command > completion > status_update > question > info_only

For command intent, also identify the sub_intent:
- draft_email: draft an email to customer
- send_email: send email immediately
- create_estimate: generate estimate/invoice
- assign: reassign the job (details = who)
- update_status: change job status (details = new status)
- schedule: schedule work (details = when)
- notify: notify someone (details = who)
- mark_done: close the job

Respond with ONLY this JSON:
{{"intent": "...", "sub_intent": "..." or null, "details": "..." or null}}"""

_EMAIL_DRAFT_PROMPT = """You are an email assistant for Pool Co, a professional pool service company.
Write professional but friendly emails. Be concise and specific.
Do NOT include a signature — it will be appended automatically.
Do NOT include greeting headers like 'Subject:' in the body.

Respond in this exact JSON format:
{{"subject": "...", "body": "..."}}
The body should be plain text (no HTML). Use natural line breaks."""

_RESOLUTION_PROMPT = """A pool service job just received a new comment. Does this resolve the job?

Action: [equipment] {job_desc}
Assigned to: unassigned

Comments:
- Tech: {comment}

Latest comment by Tech: "{comment}"

Respond with JSON:
{{
  "resolved": true/false,
  "update_description": null,
  "update_type": null,
  "reason": "brief explanation"
}}

Rules:
- resolved=true if: work is completed, answer was provided, task is no longer needed
- resolved=false if: just a progress update, partial work, needs more steps
- update_description: ONLY if the comment changes what needs to be done
- update_type: ONLY if action type should change"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ModelEvalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate_candidate(
        self,
        tier: str,
        candidate_model: str,
        auto_promote: bool = True,
    ) -> dict:
        """Run full eval suite against a candidate model. Auto-promote if passes."""
        current_model = await get_model(tier)
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        logger.info(f"Model eval started: tier={tier}, candidate={candidate_model}, current={current_model}, run={run_id}")

        all_results: list[dict] = []
        try:
            all_results = await self._run_test_cases(tier, candidate_model)
        except Exception as e:
            logger.error(f"Model eval crashed: {e}")
            return {
                "tier": tier,
                "candidate": candidate_model,
                "current": current_model,
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0.0,
                "threshold": OVERALL_PASS_THRESHOLD,
                "promoted": False,
                "error": str(e),
                "failures": [],
                "run_id": run_id,
            }

        total = len(all_results)
        passed = sum(1 for r in all_results if r["passed"])
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0

        # Check classifier-specific threshold
        classifier_results = [r for r in all_results if r["agent"] == "classifier"]
        classifier_passed = sum(1 for r in classifier_results if r["passed"])
        classifier_rate = classifier_passed / len(classifier_results) if classifier_results else 1.0

        # Check critical failures
        critical_failures = [r for r in all_results if not r["passed"] and r.get("critical")]

        meets_overall = pass_rate >= OVERALL_PASS_THRESHOLD
        meets_classifier = classifier_rate >= CLASSIFIER_PASS_THRESHOLD
        no_critical_failures = len(critical_failures) == 0
        should_promote = meets_overall and meets_classifier and no_critical_failures

        promoted = False
        if auto_promote and should_promote:
            try:
                await self._promote(tier, candidate_model)
                promoted = True
            except Exception as e:
                logger.error(f"Model promotion failed: {e}")

        failures = [r for r in all_results if not r["passed"]]

        result = {
            "tier": tier,
            "candidate": candidate_model,
            "current": current_model,
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 4),
            "classifier_pass_rate": round(classifier_rate, 4),
            "threshold": OVERALL_PASS_THRESHOLD,
            "classifier_threshold": CLASSIFIER_PASS_THRESHOLD,
            "critical_failures": len(critical_failures),
            "promoted": promoted,
            "failures": failures,
            "run_id": run_id,
        }

        # Log for audit trail
        await log_agent_call(
            organization_id="platform",
            agent_name="model_eval",
            action=f"evaluate_{tier}",
            input_summary=f"candidate={candidate_model}",
            output_summary=json.dumps({
                "pass_rate": result["pass_rate"],
                "promoted": promoted,
                "passed": passed,
                "failed": failed,
            }),
            success=True,
            model=candidate_model,
            duration_ms=int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
            extra_data=json.dumps(result),
        )

        # Notify if promoted
        if promoted:
            await self._notify_admins(tier, current_model, candidate_model, result)

        return result

    async def _run_test_cases(self, tier: str, candidate_model: str) -> list[dict]:
        """Run all test cases for the given tier."""
        results: list[dict] = []

        # Determine which agents use this tier
        # Fast tier: classifier, email_drafter, resolution_evaluator
        # Standard/advanced: currently no specific agents, but run classifier tests anyway
        agents_for_tier = {
            "fast": ["classifier", "email_drafter", "resolution_evaluator"],
            "standard": ["classifier"],
            "advanced": ["classifier"],
        }
        agents = agents_for_tier.get(tier, ["classifier"])

        for agent in agents:
            cases = TEST_SUITE.get(agent, [])
            for case in cases:
                try:
                    result = await asyncio.wait_for(
                        self._run_single_test(agent, case, candidate_model),
                        timeout=_EVAL_TIMEOUT,
                    )
                    results.append(result)
                except asyncio.TimeoutError:
                    results.append({
                        "agent": agent,
                        "input": _summarize_input(case),
                        "expected": str(case.get("expected", case.get("expected_resolved", ""))),
                        "got": "TIMEOUT",
                        "passed": False,
                        "critical": case.get("critical", False),
                        "error": f"Timed out after {_EVAL_TIMEOUT}s",
                    })
                except Exception as e:
                    results.append({
                        "agent": agent,
                        "input": _summarize_input(case),
                        "expected": str(case.get("expected", "")),
                        "got": "",
                        "passed": False,
                        "critical": case.get("critical", False),
                        "error": str(e),
                    })

        return results

    async def _run_single_test(self, agent: str, case: dict, candidate_model: str) -> dict:
        """Run a single test case against the candidate model."""
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        if agent == "classifier":
            return await self._test_classifier(client, case, candidate_model)
        elif agent == "email_drafter":
            return await self._test_email_drafter(client, case, candidate_model)
        elif agent == "resolution_evaluator":
            return await self._test_resolution(client, case, candidate_model)
        else:
            return {
                "agent": agent, "input": "", "expected": "", "got": "",
                "passed": False, "critical": False, "error": f"No test runner for {agent}",
            }

    async def _test_classifier(self, client: anthropic.Anthropic, case: dict, model: str) -> dict:
        """Test classifier with candidate model."""
        prompt = _CLASSIFIER_PROMPT.format(comment=case["input"])

        response = client.messages.create(
            model=model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return {
                "agent": "classifier",
                "input": case["input"],
                "expected": json.dumps(case["expected"]),
                "got": text[:200],
                "passed": False,
                "critical": case.get("critical", False),
                "error": "No JSON in response",
            }

        data = json.loads(json_match.group())
        expected = case["expected"]
        passed = True

        for field, expected_val in expected.items():
            actual_val = data.get(field)
            if actual_val != expected_val:
                passed = False
                break

        return {
            "agent": "classifier",
            "input": case["input"],
            "expected": json.dumps(expected),
            "got": json.dumps({k: data.get(k) for k in expected}),
            "passed": passed,
            "critical": case.get("critical", False),
        }

    async def _test_email_drafter(self, client: anthropic.Anthropic, case: dict, model: str) -> dict:
        """Test email drafter — just check it returns valid JSON with subject+body."""
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_EMAIL_DRAFT_PROMPT,
            messages=[{"role": "user", "content": f"Write a new email based on this instruction: {case['instruction']}\nGenerate both a subject line and body."}],
        )

        text = response.content[0].text.strip()
        # Strip markdown code blocks
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            parsed = json.loads(text)
            has_subject = bool(parsed.get("subject"))
            has_body = bool(parsed.get("body"))
            passed = has_subject and has_body
            got = f"subject={bool(parsed.get('subject'))}, body={bool(parsed.get('body'))}"
        except json.JSONDecodeError:
            passed = False
            got = f"Invalid JSON: {text[:100]}"

        return {
            "agent": "email_drafter",
            "input": case["instruction"],
            "expected": "valid JSON with subject + body",
            "got": got,
            "passed": passed,
            "critical": case.get("critical", False),
        }

    async def _test_resolution(self, client: anthropic.Anthropic, case: dict, model: str) -> dict:
        """Test resolution evaluator with candidate model."""
        prompt = _RESOLUTION_PROMPT.format(
            job_desc=case["job_desc"],
            comment=case["comment"],
        )

        response = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return {
                "agent": "resolution_evaluator",
                "input": case["comment"],
                "expected": str(case["expected_resolved"]),
                "got": text[:200],
                "passed": False,
                "critical": case.get("critical", False),
                "error": "No JSON in response",
            }

        data = json.loads(json_match.group())
        actual_resolved = data.get("resolved", False)
        passed = actual_resolved == case["expected_resolved"]

        return {
            "agent": "resolution_evaluator",
            "input": case["comment"],
            "expected": f"resolved={case['expected_resolved']}",
            "got": f"resolved={actual_resolved}",
            "passed": passed,
            "critical": case.get("critical", False),
        }

    async def _promote(self, tier: str, candidate_model: str) -> None:
        """Promote candidate to production."""
        await set_model(tier, candidate_model)
        logger.info(f"Model promoted: tier={tier}, model={candidate_model}")

    async def _notify_admins(
        self,
        tier: str,
        old_model: str,
        new_model: str,
        results: dict,
    ) -> None:
        """Create in-app notifications for all admin+ users across all orgs."""
        admin_roles = [OrgRole.owner, OrgRole.admin]

        org_users = (await self.db.execute(
            select(OrganizationUser).where(
                OrganizationUser.role.in_(admin_roles),
                OrganizationUser.is_active == True,
            )
        )).scalars().all()

        # Short model names for readability
        old_short = old_model.rsplit("-", 1)[0] if "-" in old_model else old_model
        new_short = new_model.rsplit("-", 1)[0] if "-" in new_model else new_model

        title = "AI Model Updated"
        body = (
            f"The {tier} AI model has been updated from {old_short} to {new_short}. "
            f"{results['passed']}/{results['total_tests']} tests passed ({results['pass_rate']:.0%})."
        )

        for ou in org_users:
            self.db.add(Notification(
                organization_id=ou.organization_id,
                user_id=ou.user_id,
                type="system",
                title=title,
                body=body,
                link="/settings",
            ))

        await self.db.commit()
        logger.info(f"Notified {len(org_users)} admin+ users about model promotion")


def _summarize_input(case: dict) -> str:
    """Extract a short input summary from a test case."""
    return case.get("input", case.get("instruction", case.get("comment", "")))[:100]
