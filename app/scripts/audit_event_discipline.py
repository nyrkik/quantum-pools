"""Phase 1 Step 13 — event-discipline enforcer.

Codifies every taxonomy / canonical-path rule we've learned through audits
so regressions fail CI instead of fail-audit-after-ship.

Rules enforced:

  R1. **Taxonomy completeness** (Phase 1 DoD #9).
      Every event_type string in a `PlatformEventService.emit(` call must
      appear in docs/event-taxonomy.md. Prevents silent drift where code
      emits events the doc doesn't know about.

  R2. **Payload PII-free** (Taxonomy §6).
      No emit() may have a payload key whose name suggests it carries a
      user id (user_id, assignee_id, manager_id, created_by_user_id, etc.).
      User ids live ONLY in actor_user_id, acting_as_user_id, and
      entity_refs values. The CCPA purge endpoint depends on this.

  R3. **Single job-creation path** (CLAUDE.md).
      `AgentAction(` raw constructors outside `agent_action_service.py`
      bypass `add_job()` and skip the `job.created` emit. Route every
      job creation through `AgentActionService.add_job()`.

  R4. **Event writes go through the service** (Phase 1 §5).
      No raw `INSERT INTO platform_events` outside PlatformEventService.
      The service handles payload sizing, idempotency, context
      correlation — bypassing it loses those guarantees.

  R5. **Every AI agent learns** (DNA rule #2, feedback_every_agent_learns.md).
      Every `.messages.create(` Anthropic call in a service file must be
      accompanied by `AgentLearningService` usage in the same module.
      Static AI agents are commoditized; learning is the moat.

  R6. **No stale `requires_confirmation` strings** (Phase 2 Step 11).
      After Phase 2 Step 10 migrated all DeepBlue tools to the proposals
      pipeline, any lingering `requires_confirmation` string in
      app/src/ signals a regression — either a not-yet-migrated tool
      was re-added or someone restored the legacy pattern. Block at CI.

  R7. **No `.draft_response` attribute access** (Phase 5 Step 5 closeout).
      AI draft replies live exclusively on `agent_proposals` rows with
      `entity_type='email_reply'`. Any `.draft_response` read or write on
      `AgentMessage` in app/src/ signals a regression back to the legacy
      path. The column itself stays pending Phase 5b schema drop; only
      runtime attribute access is prohibited.

Exit code:
  0 — no violations
  1 — one or more violations found

Usage:
  python app/scripts/audit_event_discipline.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_SRC = REPO_ROOT / "app" / "src"
TAXONOMY_MD = REPO_ROOT / "docs" / "event-taxonomy.md"
BASELINE_FILE = REPO_ROOT / "app" / "scripts" / "audit_event_discipline_baseline.txt"

# ---------------------------------------------------------------------------
# Allow-lists (curated exceptions with justification).
# Additions require a comment explaining *why* the exception exists.
# ---------------------------------------------------------------------------

# Files allowed to raw-construct AgentAction (the canonical path owns R3).
R3_ALLOWED_FILES = {
    # The service itself owns the canonical path.
    "app/src/services/agent_action_service.py",
    # Model definition.
    "app/src/models/agent_action.py",
}

# Files allowed to write platform_events directly (the service owns R4).
R4_ALLOWED_FILES = {
    "app/src/services/events/platform_event_service.py",
    # Backfill script — historical replay uses its own deterministic path.
    "app/scripts/backfill_platform_events.py",
    # The audit script itself — its regex contains "INSERT INTO platform_events"
    # as a string literal and would trigger its own R4 check.
    "app/scripts/audit_event_discipline.py",
}

# Payload keys that would normally carry a user id. Match on the KEY NAME —
# the rule is "no user ids in payload values," so we detect shape-of-key.
PII_PAYLOAD_KEY_PATTERNS = [
    r"\buser_id\b",
    r"\bassignee_id\b",            # prior_assignee_id, assignee_id, etc.
    r"\bassignee_user_id\b",
    r"\bmanager_id\b",             # prior_manager_id, manager_id
    r"\bmanager_user_id\b",        # prior_manager_user_id, new_manager_user_id
    r"\bcreated_by_user_id\b",
    r"\brequested_by_user_id\b",
    r"\btech_user_id\b",           # chemistry dose attribution
]

# Event-type strings permitted to be emitted without a taxonomy entry.
# Use sparingly — "test.*" is OK inside unit tests; actual product events
# should never be on this list.
R1_ALLOWED_EVENT_PREFIXES = ["test."]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str       # "R1" .. "R5"
    file: str       # relative path
    line: int
    message: str


@dataclass
class AuditReport:
    violations: list[Violation] = field(default_factory=list)

    def add(self, rule: str, file: str, line: int, message: str):
        self.violations.append(Violation(rule, file, line, message))

    def by_rule(self) -> dict[str, list[Violation]]:
        out: dict[str, list[Violation]] = {}
        for v in self.violations:
            out.setdefault(v.rule, []).append(v)
        return out


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if ".venv" in p.parts or "venv" in p.parts:
            continue
        yield p


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def _load_taxonomy_event_types() -> set[str]:
    r"""Parse docs/event-taxonomy.md and grab every event_type in a
    table row whose first cell is a backticked token.

    Row shape: ``| `thread.archived` | user_action | ...``
    """
    if not TAXONOMY_MD.exists():
        print(f"FATAL: {TAXONOMY_MD} not found", file=sys.stderr)
        sys.exit(2)
    text = TAXONOMY_MD.read_text()
    # `| `event.type` |` — the first backticked token per table row.
    pattern = re.compile(r"^\|\s*`([a-z][a-z0-9_.]+)`", re.MULTILINE)
    return set(pattern.findall(text))


_EMIT_CALL_RE = re.compile(
    r"PlatformEventService\.emit\s*\(", re.MULTILINE,
)
_EVENT_TYPE_ARG_RE = re.compile(
    r'event_type\s*=\s*["\']([a-z][a-z0-9_.]+)["\']'
)
_PAYLOAD_ARG_RE = re.compile(
    r"payload\s*=\s*(\{[^}]*\})", re.DOTALL,
)


def rule_1_taxonomy_completeness(report: AuditReport, taxonomy: set[str]):
    """Every event_type passed to emit() must appear in the taxonomy."""
    for py in _iter_py_files(APP_SRC):
        text = py.read_text()
        for m in _EMIT_CALL_RE.finditer(text):
            # Look at a window after the emit( call for the event_type kwarg.
            window = text[m.end():m.end() + 600]
            etype_match = _EVENT_TYPE_ARG_RE.search(window)
            if not etype_match:
                continue
            etype = etype_match.group(1)
            if any(etype.startswith(p) for p in R1_ALLOWED_EVENT_PREFIXES):
                continue
            if etype in taxonomy:
                continue
            line = text[:m.start()].count("\n") + 1
            report.add(
                "R1", _rel(py), line,
                f"event_type {etype!r} not in taxonomy — add to docs/event-taxonomy.md",
            )


def rule_2_payload_pii(report: AuditReport):
    """No payload keys that carry user ids — they belong in entity_refs."""
    pii_re = re.compile("|".join(f"\"{p}\"|'{p}'" for p in PII_PAYLOAD_KEY_PATTERNS))
    for py in _iter_py_files(APP_SRC):
        text = py.read_text()
        for m in _EMIT_CALL_RE.finditer(text):
            window = text[m.end():m.end() + 1200]
            payload_match = _PAYLOAD_ARG_RE.search(window)
            if not payload_match:
                continue
            payload_block = payload_match.group(1)
            bad = pii_re.search(payload_block)
            if not bad:
                continue
            line = text[:m.start()].count("\n") + 1
            report.add(
                "R2", _rel(py), line,
                f"payload contains user-id key ({bad.group(0)}) — "
                "move to entity_refs per taxonomy §6",
            )


_AGENT_ACTION_RE = re.compile(r"\bAgentAction\s*\(", re.MULTILINE)


def rule_3_single_job_path(report: AuditReport):
    """Raw AgentAction(...) constructors in services/API bypass add_job()."""
    for py in _iter_py_files(APP_SRC):
        rel = _rel(py)
        if rel in R3_ALLOWED_FILES:
            continue
        text = py.read_text()
        for m in _AGENT_ACTION_RE.finditer(text):
            # Exclude reads: `AgentAction` inside select(AgentAction), etc.
            preceding = text[max(0, m.start() - 20):m.start()]
            if preceding.endswith(("select(", "from src.models", "update(", "delete(", "insert(", "update(", ".where(")):
                continue
            # Skip if it's a type reference (AgentActionComment, etc.)
            trailing = text[m.end():m.end() + 1]
            full = text[m.start():m.end()]
            line = text[:m.start()].count("\n") + 1
            # The `AgentAction(` match is only a row-construction when it's
            # followed by keyword-style arguments across multiple lines.
            # A simpler heuristic: if the next ~200 chars contain `=`
            # keyword-argument pattern typical of model construction.
            snippet = text[m.start():m.start() + 400]
            if re.search(r"\borganization_id\s*=", snippet):
                report.add(
                    "R3", rel, line,
                    "raw AgentAction(...) construction — route through "
                    "AgentActionService.add_job() for job.created emit",
                )


_INSERT_PLATFORM_EVENTS_RE = re.compile(
    r"INSERT\s+INTO\s+platform_events", re.IGNORECASE,
)


def rule_4_single_emit_path(report: AuditReport):
    """Raw INSERT INTO platform_events outside the emit service."""
    search_roots = [APP_SRC, REPO_ROOT / "app" / "scripts"]
    for root in search_roots:
        for py in _iter_py_files(root):
            rel = _rel(py)
            if rel in R4_ALLOWED_FILES:
                continue
            text = py.read_text()
            for m in _INSERT_PLATFORM_EVENTS_RE.finditer(text):
                line = text[:m.start()].count("\n") + 1
                report.add(
                    "R4", rel, line,
                    "raw INSERT into platform_events — use "
                    "PlatformEventService.emit() to get payload sizing, "
                    "idempotency, and context correlation",
                )


_ANTHROPIC_CALL_RE = re.compile(r"\.messages\.create\s*\(")


_REQUIRES_CONFIRM_RE = re.compile(r'\brequires_confirmation\b')
_DRAFT_RESPONSE_ATTR_RE = re.compile(r'\.draft_response\b')


def rule_7_no_draft_response_attr_access(report: AuditReport):
    """After Phase 5 Step 5, `AgentMessage.draft_response` has no runtime
    read/write — drafts live on `agent_proposals`. Catches regressions of
    `msg.draft_response = ...` or `msg.draft_response` reads. The column
    stays pending Phase 5b; we police attribute access, not column exist."""
    for py in _iter_py_files(APP_SRC):
        rel = _rel(py)
        text = py.read_text()
        # Allow mention in the model's own definition + in this enforcer.
        if rel in ("app/src/models/agent_message.py",
                   "app/scripts/audit_event_discipline.py"):
            continue
        for m in _DRAFT_RESPONSE_ATTR_RE.finditer(text):
            line = text[:m.start()].count("\n") + 1
            report.add(
                "R7", rel, line,
                "`.draft_response` attribute access is retired — drafts live "
                "on agent_proposals(entity_type='email_reply')",
            )


def rule_6_no_stale_requires_confirmation(report: AuditReport):
    """The requires_confirmation pattern is retired as of Phase 2 Step 10.
    Any occurrence in app/src/ signals a regression."""
    for py in _iter_py_files(APP_SRC):
        rel = _rel(py)
        text = py.read_text()
        for m in _REQUIRES_CONFIRM_RE.finditer(text):
            # Allow mention in this script's own comments + docstrings
            # (we have to name the pattern to detect it).
            if rel == "app/scripts/audit_event_discipline.py":
                continue
            line = text[:m.start()].count("\n") + 1
            report.add(
                "R6", rel, line,
                "'requires_confirmation' pattern is retired — use ProposalService.stage "
                "and return proposal_id instead",
            )


def rule_5_every_agent_learns(report: AuditReport):
    """Each `.messages.create(` in a service must have AgentLearningService
    imported + used in the same file (heuristic — the learner needs to be
    referenced; whether it's pre-gen or post-gen is the author's choice but
    SOMETHING must connect this LLM call to the feedback loop)."""
    services_dir = APP_SRC / "services"
    for py in _iter_py_files(services_dir):
        text = py.read_text()
        if not _ANTHROPIC_CALL_RE.search(text):
            continue
        # File has an LLM call. Does it also reference the learning service?
        uses_learner = (
            "AgentLearningService" in text
            or "agent_learning_service" in text
        )
        if uses_learner:
            continue
        # Get the first LLM call for the line number.
        m = _ANTHROPIC_CALL_RE.search(text)
        line = text[:m.start()].count("\n") + 1
        report.add(
            "R5", _rel(py), line,
            f".messages.create() without AgentLearningService in module — "
            "DNA rule #2: every AI agent learns",
        )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _violation_key(v: Violation) -> str:
    """Stable identifier for baseline comparison. Line-number-free so a
    baseline-allowlisted violation stays allowlisted across unrelated
    edits to the same file."""
    return f"{v.rule}|{v.file}|{v.message}"


def _load_baseline() -> set[str]:
    if not BASELINE_FILE.exists():
        return set()
    out: set[str] = set()
    for line in BASELINE_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def _write_baseline(violations: list[Violation]):
    header = [
        "# Event-discipline enforcer baseline.",
        "# Each line = one pre-existing violation that predates the audit.",
        "# Format: <rule>|<file>|<message>",
        "# Lines starting with # are comments.",
        "#",
        "# To add a NEW exception: run `--write-baseline` AFTER a deliberate decision.",
        "# Normal path: fix the violation, don't add it here.",
        "#",
        f"# Generated {len(violations)} entries.",
        "",
    ]
    body = sorted(_violation_key(v) for v in violations)
    BASELINE_FILE.write_text("\n".join(header + body) + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="Write current violations as the new baseline (debt snapshot). "
        "Use sparingly — normal flow is 'fix, don't allowlist'.",
    )
    args = parser.parse_args()

    taxonomy = _load_taxonomy_event_types()
    report = AuditReport()

    rule_1_taxonomy_completeness(report, taxonomy)
    rule_2_payload_pii(report)
    rule_3_single_job_path(report)
    rule_4_single_emit_path(report)
    rule_5_every_agent_learns(report)
    rule_6_no_stale_requires_confirmation(report)
    rule_7_no_draft_response_attr_access(report)

    if args.write_baseline:
        _write_baseline(report.violations)
        print(f"✓ Wrote baseline: {len(report.violations)} entries to {BASELINE_FILE}")
        return 0

    baseline = _load_baseline()
    new_violations = [v for v in report.violations if _violation_key(v) not in baseline]
    # Baseline violations that are no longer present = debt paid down.
    current_keys = {_violation_key(v) for v in report.violations}
    resolved = baseline - current_keys

    rule_titles = {
        "R1": "Taxonomy completeness",
        "R2": "Payload PII-free",
        "R3": "Single job-creation path",
        "R4": "Single emit path",
        "R5": "Every AI agent learns",
        "R6": "No stale requires_confirmation",
        "R7": "No .draft_response attribute access",
    }

    if resolved:
        print(f"✓ {len(resolved)} baseline violation(s) resolved — "
              f"shrink the baseline with --write-baseline.\n")

    if not new_violations:
        print(f"✓ Event discipline audit PASSED")
        print(f"  Taxonomy: {len(taxonomy)} documented event types")
        print(f"  Rules checked: R1 R2 R3 R4 R5 R6 R7")
        print(f"  Baseline debt: {len(baseline)} (allowlisted)")
        return 0

    print(f"✗ Event discipline audit FAILED — {len(new_violations)} NEW violation(s)")
    print(f"  (baseline debt: {len(baseline)} allowlisted)\n")
    by_rule: dict[str, list[Violation]] = {}
    for v in new_violations:
        by_rule.setdefault(v.rule, []).append(v)
    for rule, violations in sorted(by_rule.items()):
        print(f"== {rule} ({rule_titles[rule]}) — {len(violations)} ==")
        for v in violations:
            print(f"  {v.file}:{v.line}  {v.message}")
        print()
    print("If the violation is legitimately pre-existing, add an exception to "
          "R{1..5}_ALLOWED_*. Do NOT blanket-allowlist new drift.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
