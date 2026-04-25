"""InboxRulesService — unified sender/recipient pattern matching.

Replaces the older split between `inbox_routing_rules` (block + route rules)
and `suppressed_email_senders` (tag + folder routing). See
`docs/inbox-rules-unification-plan.md` for the migration rationale and
the scppool incident that prompted consolidation.

A single entry point (`evaluate`) loads every active rule for the org,
tests each rule's conditions against the message/thread context, and
returns the accumulated actions in priority order. `apply` executes those
actions against a thread.

Design notes:
- Rules are NOT exclusive: multiple rules can fire on the same message.
  Actions from all matching rules are concatenated, then applied in the
  order priority-ASC, rule-created-ASC. Later actions of the same type
  override earlier ones (last-write-wins per-type).
- `evaluate` is read-only and cheap — callers can run it at ingest time
  and again at display time (thread presenter) without worrying about
  side effects.
- `apply` is write-only and should be called at most once per message
  during the orchestrator pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.inbox_rule import InboxRule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public action type constants. Keep the orchestrator / presenter / UI in
# sync with this list. Don't inline strings.
# ---------------------------------------------------------------------------
ACTION_ASSIGN_FOLDER = "assign_folder"
ACTION_ASSIGN_TAG = "assign_tag"
ACTION_ASSIGN_CATEGORY = "assign_category"
ACTION_SET_VISIBILITY = "set_visibility"
ACTION_SUPPRESS_CONTACT_PROMPT = "suppress_contact_prompt"
ACTION_ROUTE_TO_SPAM = "route_to_spam"
ACTION_MARK_AS_READ = "mark_as_read"
# Advisory flag — NOT a thread mutation. Tells customer_matcher to skip its
# "previous match reuse" shortcut for this sender. Used for regional /
# corporate / shared senders (e.g. a property management executive assistant
# covering multiple customer properties) where step 2 would incorrectly pin
# them to whichever customer their last thread happened to reference.
ACTION_SKIP_CUSTOMER_MATCH = "skip_customer_match"

ALL_ACTION_TYPES = {
    ACTION_ASSIGN_FOLDER,
    ACTION_ASSIGN_TAG,
    ACTION_ASSIGN_CATEGORY,
    ACTION_SET_VISIBILITY,
    ACTION_SUPPRESS_CONTACT_PROMPT,
    ACTION_ROUTE_TO_SPAM,
    ACTION_MARK_AS_READ,
    ACTION_SKIP_CUSTOMER_MATCH,
}

# Fields a condition can match against. Keep in sync with the UI.
ALL_CONDITION_FIELDS = {
    "sender_email",
    "sender_domain",
    "recipient_email",
    "subject",
    "category",
    "customer_id",
    # Virtual field derived from the matcher: "yes" when the thread has a
    # matched_customer_id, "no" when unmatched. Lets a rule say "any client
    # → Clients folder" as a sibling of the explicit customer_id=<uuid> form.
    "customer_matched",
    "body",
}

# Operator implementations. Each takes (haystack, needle) and returns bool.
# `haystack` is whatever the context provides for the field; `needle` is the
# rule's `value`. Both are lowercased first for case-insensitive matching.
_OPERATORS = {
    "equals": lambda h, n: h == n,
    "contains": lambda h, n: n in h,
    "starts_with": lambda h, n: h.startswith(n),
    "ends_with": lambda h, n: h.endswith(n),
    "matches": lambda h, n: _glob_match(h, n),
}


def _glob_match(haystack: str, pattern: str) -> bool:
    """Minimal glob: `*@domain.com`, `prefix-*`, `*suffix`, `*mid*`. No regex."""
    if "*" not in pattern:
        return haystack == pattern
    # Split on '*' and verify each chunk appears in order.
    parts = pattern.split("*")
    pos = 0
    # Anchored prefix (pattern doesn't start with '*')
    if parts[0] and not haystack.startswith(parts[0]):
        return False
    if parts[0]:
        pos = len(parts[0])
    # Middle chunks appear in order
    for chunk in parts[1:-1]:
        idx = haystack.find(chunk, pos)
        if idx == -1:
            return False
        pos = idx + len(chunk)
    # Anchored suffix (pattern doesn't end with '*')
    if parts[-1] and not haystack.endswith(parts[-1]):
        return False
    return True


class InboxRulesService:
    """Single source of truth for sender/recipient pattern matching.

    Usage:
        svc = InboxRulesService(db)
        actions = await svc.evaluate(context, org_id)
        await svc.apply(actions, thread, db)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate(self, context: dict, org_id: str) -> list[dict]:
        """Return matching actions in priority order for this message.

        `context` is a dict with the fields listed in ALL_CONDITION_FIELDS.
        Missing fields are treated as absent (no condition referencing them
        can match).
        """
        rules = (await self.db.execute(
            select(InboxRule)
            .where(
                InboxRule.organization_id == org_id,
                InboxRule.is_active.is_(True),
            )
            .order_by(InboxRule.priority.asc(), InboxRule.created_at.asc())
        )).scalars().all()

        matched_actions: list[dict] = []
        for rule in rules:
            if self._matches(rule.conditions or [], context):
                for action in (rule.actions or []):
                    # Tag the action with its source rule id so callers can
                    # audit / display "this folder assignment came from rule X".
                    matched_actions.append({**action, "_rule_id": rule.id})
        return matched_actions

    def _matches(self, conditions: Iterable[dict], context: dict) -> bool:
        """Return True iff every condition in the rule matches the context.

        A condition's ``value`` can be a scalar string or a list of strings.
        List values match when ANY element satisfies the operator — the
        equivalent of "sender contains any of [foo, bar, baz]". This lets
        one rule collapse what used to require N parallel rules.
        """
        for cond in conditions:
            field = (cond.get("field") or "").strip()
            operator = (cond.get("operator") or "").strip()
            value = cond.get("value")
            if field not in ALL_CONDITION_FIELDS or operator not in _OPERATORS:
                # Unknown schema — fail closed rather than matching by default.
                return False
            haystack = context.get(field)
            if haystack is None or value is None:
                return False
            haystack_lower = str(haystack).lower()
            candidates = value if isinstance(value, list) else [value]
            if not any(
                _OPERATORS[operator](haystack_lower, str(v).lower())
                for v in candidates
                if v is not None and str(v) != ""
            ):
                return False
        return True

    # ------------------------------------------------------------------
    # Sender-level rule upsert / delete — shared by the bulk-spam,
    # sender-tag, and dismiss-contact-prompt endpoints. Each creates or
    # replaces a single rule keyed on the sender pattern.
    # ------------------------------------------------------------------

    async def upsert_sender_rule(
        self,
        org_id: str,
        sender_pattern: str,
        actions: list[dict],
        *,
        name: str | None = None,
        created_by: str | None = None,
    ) -> "InboxRule":
        """Create or replace a rule whose sole condition is `sender_email
        equals <sender_pattern>` (or `sender_domain matches <pattern>` for
        `*@domain` inputs). Actions fully replace the existing rule's
        action list so callers don't need to read-modify-write.

        Wildcard `*@domain.com` patterns are stored as a `sender_domain
        matches` condition so the evaluator treats them as a domain glob.
        """
        import uuid

        pattern = (sender_pattern or "").strip().lower()
        if not pattern:
            raise ValueError("sender_pattern is required")

        if pattern.startswith("*@"):
            condition = {
                "field": "sender_domain",
                "operator": "matches",
                "value": pattern,
            }
        else:
            condition = {
                "field": "sender_email",
                "operator": "equals",
                "value": pattern,
            }

        existing = (await self.db.execute(
            select(InboxRule).where(
                InboxRule.organization_id == org_id,
                InboxRule.conditions.contains([condition]),
            ).limit(1)
        )).scalar_one_or_none()

        if existing:
            existing.actions = list(actions)
            if name:
                existing.name = name
            rule = existing
        else:
            max_priority = (await self.db.execute(
                select(InboxRule.priority)
                .where(InboxRule.organization_id == org_id)
                .order_by(InboxRule.priority.desc())
                .limit(1)
            )).scalar()
            rule = InboxRule(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                name=name or f"Sender: {pattern}",
                priority=(max_priority or 0) + 10,
                conditions=[condition],
                actions=list(actions),
                is_active=True,
                created_by=created_by or "api",
            )
            self.db.add(rule)

        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def delete_sender_rules(self, org_id: str, sender_pattern: str) -> int:
        """Delete every rule whose sole condition targets this sender
        pattern (exact or domain-glob). Returns rows removed."""
        from sqlalchemy import delete as sql_delete

        pattern = (sender_pattern or "").strip().lower()
        if not pattern:
            return 0

        conditions = []
        if pattern.startswith("*@"):
            conditions.append({
                "field": "sender_domain", "operator": "matches", "value": pattern,
            })
        else:
            conditions.append({
                "field": "sender_email", "operator": "equals", "value": pattern,
            })

        rows = (await self.db.execute(
            select(InboxRule).where(
                InboxRule.organization_id == org_id,
                InboxRule.conditions.contains(conditions),
            )
        )).scalars().all()
        removed = 0
        for r in rows:
            await self.db.execute(sql_delete(InboxRule).where(InboxRule.id == r.id))
            removed += 1
        if removed:
            await self.db.commit()
        return removed

    # ------------------------------------------------------------------
    # Convenience helpers — replace existing lookup call sites.
    # ------------------------------------------------------------------

    async def get_sender_tag(self, sender_email: str, org_id: str) -> str | None:
        """Return the first `assign_tag` action for this sender, or None.

        Replaces the `SuppressedEmailSender`-based lookup in
        `thread_presenter` and related code.
        """
        if not sender_email:
            return None
        ctx = _context_from_sender(sender_email)
        for action in await self.evaluate(ctx, org_id):
            if action.get("type") == ACTION_ASSIGN_TAG:
                tag = (action.get("params") or {}).get("tag")
                if tag:
                    return tag
        return None

    async def get_folder_for_sender(
        self, sender_email: str, org_id: str
    ) -> str | None:
        """Folder id a rule wants a sender routed to, or None."""
        if not sender_email:
            return None
        ctx = _context_from_sender(sender_email)
        for action in await self.evaluate(ctx, org_id):
            if action.get("type") == ACTION_ASSIGN_FOLDER:
                folder_id = (action.get("params") or {}).get("folder_id")
                if folder_id:
                    return folder_id
            if action.get("type") == ACTION_ROUTE_TO_SPAM:
                return "__spam__"  # sentinel; caller resolves to Spam folder id
        return None

    # ------------------------------------------------------------------
    # Auto-handled banner support — "Yes, add to existing rule" promotion
    # ------------------------------------------------------------------

    async def preview_append_match(
        self,
        org_id: str,
        sender_email: str,
        folder_id: str | None,
        spam_folder_id: str | None = None,
    ) -> dict:
        """Look for a rule this auto-handled thread could be appended to.

        Return one of three states:

        * ``covered`` — an existing active rule already catches this sender.
          The user clicking "Yes" is redundant; banner just acknowledges.
        * ``promotable`` — exactly one active rule has an action matching
          where the thread landed (same assign_folder id, or route_to_spam
          when the thread is in Spam), has a single sender-based condition,
          and doesn't yet cover this sender. Safe to append with one click.
        * ``unclear`` — no matching rule, ambiguous (2+ matches), or the
          sender can't be normalized. Banner falls back to Create-rule.

        Returns ``{state, rule_id?, rule_name?, append_value?}``.
        """
        sender = (sender_email or "").lower().strip()
        if not sender or "@" not in sender:
            return {"state": "unclear"}

        rules = (await self.db.execute(
            select(InboxRule).where(
                InboxRule.organization_id == org_id,
                InboxRule.is_active.is_(True),
            )
        )).scalars().all()

        covered_rule: InboxRule | None = None
        candidates: list[InboxRule] = []

        for rule in rules:
            conds = rule.conditions or []
            if len(conds) != 1:
                continue
            cond = conds[0]
            field = cond.get("field")
            operator = cond.get("operator")
            if field not in ("sender_email", "sender_domain"):
                continue
            if operator not in _OPERATORS:
                continue

            # Does this rule's action match where the AI put the thread?
            action_matches = False
            for action in (rule.actions or []):
                atype = action.get("type")
                if atype == ACTION_ASSIGN_FOLDER:
                    target = (action.get("params") or {}).get("folder_id")
                    if target and target == folder_id:
                        action_matches = True
                        break
                elif atype == ACTION_ROUTE_TO_SPAM:
                    if spam_folder_id and folder_id == spam_folder_id:
                        action_matches = True
                        break
            if not action_matches:
                continue

            # Does this rule already catch this sender?
            value = cond.get("value")
            values = value if isinstance(value, list) else ([value] if value else [])
            haystack = sender if field == "sender_email" else sender.split("@", 1)[-1]
            already_covered = any(
                v is not None
                and str(v) != ""
                and _OPERATORS[operator](haystack, str(v).lower())
                for v in values
            )
            if already_covered:
                covered_rule = rule
                break  # first-match wins for the covered state
            candidates.append(rule)

        if covered_rule is not None:
            return {
                "state": "covered",
                "rule_id": covered_rule.id,
                "rule_name": covered_rule.name,
            }

        if len(candidates) != 1:
            return {"state": "unclear"}

        rule = candidates[0]
        cond = (rule.conditions or [])[0]
        field = cond.get("field")
        operator = cond.get("operator")
        domain = sender.split("@", 1)[-1]

        # Pick the value to append based on the rule's own operator/field so
        # the appended value has the same semantics as the existing ones.
        if field == "sender_domain":
            append = domain
        elif operator == "equals":
            append = sender
        elif operator in ("contains", "ends_with"):
            append = f"@{domain}" if operator == "ends_with" else domain
        elif operator == "starts_with":
            append = sender  # rare; safest to use full address
        else:
            append = sender

        return {
            "state": "promotable",
            "rule_id": rule.id,
            "rule_name": rule.name,
            "append_value": append,
        }

    async def append_sender_to_rule(
        self,
        org_id: str,
        rule_id: str,
        value: str,
    ) -> dict:
        """Append ``value`` to the first sender-based condition of ``rule_id``.

        No-op if value is already present (covered). Promotes a scalar value
        to an array when needed. Returns ``{rule_id, appended, already}``.
        """
        value_clean = (value or "").strip().lower()
        if not value_clean:
            raise ValueError("value is required")

        rule = (await self.db.execute(
            select(InboxRule).where(
                InboxRule.id == rule_id,
                InboxRule.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if rule is None:
            raise ValueError("rule not found")

        conds = list(rule.conditions or [])
        target_idx: int | None = None
        for i, c in enumerate(conds):
            if c.get("field") in ("sender_email", "sender_domain"):
                target_idx = i
                break
        if target_idx is None:
            raise ValueError("rule has no sender-based condition")

        cond = dict(conds[target_idx])
        existing = cond.get("value")
        values: list[str] = (
            [str(v) for v in existing if v is not None]
            if isinstance(existing, list)
            else ([str(existing)] if existing else [])
        )

        if value_clean in [v.lower() for v in values]:
            return {"rule_id": rule.id, "appended": False, "already": True}

        values.append(value_clean)
        cond["value"] = values if len(values) > 1 else values[0]
        conds[target_idx] = cond
        rule.conditions = conds
        # Force SQLAlchemy JSONB mutation flag — assigning a new list does
        # this in practice but be explicit to survive future ORM quirks.
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(rule, "conditions")
        await self.db.commit()
        return {"rule_id": rule.id, "appended": True, "already": False}

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    async def apply_to_existing_threads(
        self,
        rule_id: str,
        org_id: str,
        *,
        dry_run: bool = False,
        sample_size: int = 5,
    ) -> dict:
        """Back-apply a single rule to threads already in the inbox.

        Workflow when the user creates a rule like "from billing@stripe.com
        → folder Billing": today the rule only fires on NEW inbound; old
        Stripe threads stay where they are. This method finds every live
        non-historical thread matching the rule's conditions and runs the
        rule's actions against them.

        Skipped:
          * historical threads (pre-cutover ingest)
          * threads with `folder_override=True` for ASSIGN_FOLDER /
            ROUTE_TO_SPAM actions (user manually moved them; respect that)
          * `body` conditions — would require loading every message body;
            currently unsupported retroactively. Logged for the caller.
          * advisory action types (assign_tag, suppress_contact_prompt,
            skip_customer_match) — they don't mutate threads, so retro
            application is a no-op.

        Returns ``{matched, applied, skipped_overrides, has_body_condition,
        sample[]}`` where ``sample`` is up to ``sample_size`` thread refs
        for preview surfaces.
        """
        rule = (await self.db.execute(
            select(InboxRule).where(
                InboxRule.id == rule_id,
                InboxRule.organization_id == org_id,
            )
        )).scalar_one_or_none()
        if not rule:
            return {
                "matched": 0, "applied": 0, "skipped_overrides": 0,
                "has_body_condition": False, "sample": [],
            }

        conditions = rule.conditions or []
        actions = rule.actions or []
        has_body_condition = any(
            (c.get("field") or "") == "body" for c in conditions
        )

        # Mutating actions only — advisory types are excluded so we don't
        # produce misleading "applied" counts when the rule is, say, a
        # pure assign_tag. Tag/sender-tag display is read-time anyway.
        mutating_action_types = {
            ACTION_ASSIGN_FOLDER, ACTION_ROUTE_TO_SPAM,
            ACTION_ASSIGN_CATEGORY, ACTION_SET_VISIBILITY,
            ACTION_MARK_AS_READ,
        }
        mutates_thread = any(
            a.get("type") in mutating_action_types for a in actions
        )

        # Resolve spam folder once for this org so the per-thread loop
        # doesn't re-query.
        spam_folder_id: str | None = None
        if any(a.get("type") == ACTION_ROUTE_TO_SPAM for a in actions):
            from src.models.inbox_folder import InboxFolder
            spam_folder_id = (await self.db.execute(
                select(InboxFolder.id).where(
                    InboxFolder.organization_id == org_id,
                    InboxFolder.system_key == "spam",
                )
            )).scalar_one_or_none()

        # Whether ASSIGN_FOLDER / ROUTE_TO_SPAM is in this rule — drives
        # the folder_override skip below.
        moves_folder = any(
            a.get("type") in (ACTION_ASSIGN_FOLDER, ACTION_ROUTE_TO_SPAM)
            for a in actions
        )

        # Tagged actions for the per-thread apply call (apply expects the
        # full action list with _rule_id annotated).
        tagged_actions = [{**a, "_rule_id": rule.id} for a in actions]

        from src.models.agent_thread import AgentThread
        threads_q = (
            select(AgentThread).where(
                AgentThread.organization_id == org_id,
                AgentThread.is_historical == False,  # noqa: E712
            ).order_by(AgentThread.last_message_at.desc())
        )
        threads = (await self.db.execute(threads_q)).scalars().all()

        matched = 0
        applied = 0
        skipped_overrides = 0
        sample: list[dict] = []

        for t in threads:
            ctx = build_context(
                sender_email=t.contact_email,
                recipient_email=t.delivered_to,
                subject=t.subject,
                category=t.category,
                customer_id=t.matched_customer_id,
                # body intentionally omitted — see method docstring
            )
            if not self._matches(conditions, ctx):
                continue
            matched += 1

            if moves_folder and t.folder_override:
                skipped_overrides += 1
                continue

            if len(sample) < sample_size:
                sample.append({
                    "thread_id": t.id,
                    "subject": t.subject,
                    "contact_email": t.contact_email,
                    "current_folder_id": t.folder_id,
                })

            if dry_run or not mutates_thread:
                continue

            await self.apply(tagged_actions, t, spam_folder_id=spam_folder_id)
            applied += 1

        if not dry_run and applied > 0:
            await self.db.commit()

        return {
            "matched": matched,
            "applied": applied,
            "skipped_overrides": skipped_overrides,
            "has_body_condition": has_body_condition,
            "mutates_thread": mutates_thread,
            "sample": sample,
        }

    async def apply(
        self,
        actions: list[dict],
        thread: Any,
        *,
        spam_folder_id: str | None = None,
    ) -> None:
        """Mutate `thread` according to the matched actions.

        Caller is responsible for commit. Designed for use inside the
        orchestrator pipeline where we batch a commit across multiple
        operations.

        `spam_folder_id` — the Spam system folder id for this org, passed
        in so we don't need a second query from inside this helper.
        """
        if not actions:
            return

        # Apply in order; last action of a given type wins for per-field sets.
        for action in actions:
            atype = action.get("type")
            params = action.get("params") or {}

            if atype == ACTION_ASSIGN_FOLDER:
                folder_id = params.get("folder_id")
                if folder_id and hasattr(thread, "folder_id"):
                    thread.folder_id = folder_id

            elif atype == ACTION_ROUTE_TO_SPAM:
                if spam_folder_id and hasattr(thread, "folder_id"):
                    thread.folder_id = spam_folder_id

            elif atype == ACTION_ASSIGN_CATEGORY:
                category = params.get("category")
                if category and hasattr(thread, "category"):
                    thread.category = category

            elif atype == ACTION_SET_VISIBILITY:
                # Role-group list (post-migration). Empty/missing list →
                # visible to everyone in the org.
                role_slugs = params.get("role_slugs")
                if hasattr(thread, "visibility_role_slugs"):
                    thread.visibility_role_slugs = (
                        list(role_slugs) if role_slugs else None
                    )

            elif atype == ACTION_MARK_AS_READ:
                # Stamp the thread as "read for everyone up through the
                # latest message." Unread computation in the presenter /
                # stats will treat the thread as read until a new inbound
                # arrives that isn't covered by this stamp.
                if hasattr(thread, "auto_read_at") and hasattr(
                    thread, "last_message_at"
                ):
                    thread.auto_read_at = thread.last_message_at

            # ACTION_ASSIGN_TAG + ACTION_SUPPRESS_CONTACT_PROMPT +
            # ACTION_SKIP_CUSTOMER_MATCH don't mutate the thread directly —
            # they're advisory flags surfaced via get_sender_tag (for display)
            # and callers of `evaluate` respectively.


# ---------------------------------------------------------------------------
# Helpers for building a context dict from common inputs.
# ---------------------------------------------------------------------------


def _context_from_sender(sender_email: str) -> dict:
    """Minimal context keyed only on sender (used by convenience lookups)."""
    sender = (sender_email or "").lower()
    domain = sender.split("@", 1)[-1] if "@" in sender else ""
    return {
        "sender_email": sender,
        "sender_domain": domain,
    }


def build_context(
    *,
    sender_email: str | None = None,
    recipient_email: str | None = None,
    subject: str | None = None,
    category: str | None = None,
    customer_id: str | None = None,
    body: str | None = None,
) -> dict:
    """Canonical helper for constructing an evaluator context.

    All string fields are lowercased by the evaluator anyway, but we
    normalize here so tests, the orchestrator, and the presenter share
    one construction path.
    """
    sender = (sender_email or "").lower()
    domain = sender.split("@", 1)[-1] if "@" in sender else ""
    return {
        "sender_email": sender,
        "sender_domain": domain,
        "recipient_email": (recipient_email or "").lower(),
        "subject": subject or "",
        "category": category or "",
        "customer_id": customer_id or "",
        # Virtual field: "yes" if the matcher pinned a customer, "no" otherwise.
        # Lets rules route by "any client" without naming specific customer ids.
        "customer_matched": "yes" if customer_id else "no",
        "body": body or "",
    }
