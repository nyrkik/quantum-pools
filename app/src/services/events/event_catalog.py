"""Machine-readable registry of every event type in the system.

This is the code-side twin of `docs/event-taxonomy.md` — used by:
- `POST /v1/events` receiver to allowlist frontend-emitted events
- Completeness audit (Step 13) to assert new code emits documented types
- Future Sonar tooling to enumerate event types for queries

Maintenance rule (same as doc): a new event type added in code MUST be
added both here and in `docs/event-taxonomy.md` in the same PR. The /cpu
skill checks for drift.

Each entry declares:
  - `levels`: which `level` enum values are valid for this event
  - `frontend_emittable`: True if the frontend is allowed to POST this
    event via /v1/events; False means backend-only (e.g., state
    transitions, AI-generated events, errors).
  - `requires_org`: False for platform events (login_failed, etc.);
    True otherwise. Receiver enforces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Level = Literal["user_action", "system_action", "agent_action", "error"]


@dataclass(frozen=True)
class EventSpec:
    levels: frozenset[Level]
    frontend_emittable: bool = False
    requires_org: bool = True

    def allows_level(self, level: str) -> bool:
        return level in self.levels


# ---------------------------------------------------------------------------
# Catalog
#
# Organized by subsystem to mirror docs/event-taxonomy.md §8.
# ---------------------------------------------------------------------------

_U = frozenset({"user_action"})
_S = frozenset({"system_action"})
_A = frozenset({"agent_action"})
_E = frozenset({"error"})
_U_S = frozenset({"user_action", "system_action"})
_U_S_A = frozenset({"user_action", "system_action", "agent_action"})
_U_A = frozenset({"user_action", "agent_action"})


EVENT_CATALOG: dict[str, EventSpec] = {
    # --- 8.1 Inbox / Email ---
    "thread.opened": EventSpec(levels=_U, frontend_emittable=True),
    "thread.closed": EventSpec(levels=_U, frontend_emittable=True),
    "thread.archived": EventSpec(levels=_U, frontend_emittable=True),
    "thread.deleted": EventSpec(levels=_U, frontend_emittable=True),
    "thread.snoozed": EventSpec(levels=_U, frontend_emittable=True),
    "thread.unsnoozed": EventSpec(levels=_S),
    "thread.assigned": EventSpec(levels=_U, frontend_emittable=True),
    "thread.status_changed": EventSpec(levels=_U_S),
    "thread.category_changed": EventSpec(levels=_U, frontend_emittable=True),
    "thread.summarized": EventSpec(levels=_A),
    "thread.linked_to_case": EventSpec(levels=_U_S, frontend_emittable=True),
    "thread.unlinked_from_case": EventSpec(levels=_U, frontend_emittable=True),
    "thread.resolved": EventSpec(levels=_U_S),
    "thread.reopened": EventSpec(levels=_U_S),
    "thread.sla_breached": EventSpec(levels=_S),
    "thread.first_response_sent": EventSpec(levels=_U_A),
    "agent_message.received": EventSpec(levels=_S),
    "agent_message.sent": EventSpec(levels=_U),
    "agent_message.send_failed": EventSpec(levels=_E),
    "agent_message.classified": EventSpec(levels=_A),
    "agent_message.customer_matched": EventSpec(levels=_A),
    "agent_message.customer_match_overridden": EventSpec(levels=_U, frontend_emittable=True),
    "compose.opened": EventSpec(levels=_U, frontend_emittable=True),
    "compose.draft_generated": EventSpec(levels=_A),
    "compose.draft_regenerated": EventSpec(levels=_U, frontend_emittable=True),
    "compose.sent": EventSpec(levels=_U, frontend_emittable=True),
    "compose.discarded": EventSpec(levels=_U, frontend_emittable=True),
    "inbox.filter_changed": EventSpec(levels=_U, frontend_emittable=True, requires_org=False),
    "inbox.folder_viewed": EventSpec(levels=_U, frontend_emittable=True),
    "inbox.bulk_action": EventSpec(levels=_U, frontend_emittable=True),
    "inbox.compact_mode_toggled": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.2 Proposals (Phase 2 — listed for forward-compat) ---
    "proposal.staged": EventSpec(levels=_A),
    "proposal.accepted": EventSpec(levels=_U, frontend_emittable=True),
    "proposal.edited_and_accepted": EventSpec(levels=_U, frontend_emittable=True),
    "proposal.rejected": EventSpec(levels=_U, frontend_emittable=True),
    "proposal.rejected_permanently": EventSpec(levels=_U, frontend_emittable=True),
    "proposal.expired": EventSpec(levels=_S),
    "proposal.superseded": EventSpec(levels=frozenset({"system_action", "agent_action"})),

    # --- 8.3 Agents (generic) ---
    "agent.generated": EventSpec(levels=_A),
    "agent.tool_called": EventSpec(levels=_A),
    "agent.error": EventSpec(levels=_E),
    "agent.lessons_applied": EventSpec(levels=_A),
    "agent.output_edited": EventSpec(levels=_U, frontend_emittable=True),
    "agent.output_regenerated": EventSpec(levels=_U, frontend_emittable=True),
    "agent.wrong_tool_selected": EventSpec(levels=_U_S, frontend_emittable=True),
    "agent.context_truncated": EventSpec(levels=_A),

    # --- 8.4 Jobs ---
    "job.created": EventSpec(levels=_U_S_A),
    "job.status_changed": EventSpec(levels=_U_S),
    "job.assigned": EventSpec(levels=_U, frontend_emittable=True),
    "job.scheduled": EventSpec(levels=_U_S, frontend_emittable=True),
    "job.completed": EventSpec(levels=_U, frontend_emittable=True),
    "job.cancelled": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.5 Cases ---
    "case.created": EventSpec(levels=_U_S),
    "case.closed": EventSpec(levels=_U_S),
    "case.reopened": EventSpec(levels=_U, frontend_emittable=True),
    "case.manager_changed": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.6 Invoices / Estimates ---
    "invoice.created": EventSpec(levels=_U_S_A),
    "invoice.sent": EventSpec(levels=_U, frontend_emittable=True),
    "invoice.paid": EventSpec(levels=_U_S),
    "invoice.voided": EventSpec(levels=_U, frontend_emittable=True),
    "invoice.write_off": EventSpec(levels=_U, frontend_emittable=True),
    "invoice.days_to_paid": EventSpec(levels=_S),
    "estimate.approved": EventSpec(levels=_U),  # via customer approval link — not frontend UI
    "estimate.declined": EventSpec(levels=_U),
    "estimate.converted_to_invoice": EventSpec(levels=_U_S),
    "estimate.conversion_funnel": EventSpec(levels=_S, requires_org=False),

    # --- 8.7 Visits / Chemistry ---
    "visit.started": EventSpec(levels=_U, frontend_emittable=True),
    "visit.en_route.start": EventSpec(levels=_U, frontend_emittable=True),
    "visit.on_site.start": EventSpec(levels=_U, frontend_emittable=True),
    "visit.on_site.end": EventSpec(levels=_U, frontend_emittable=True),
    "visit.completed": EventSpec(levels=_U, frontend_emittable=True),
    "visit.cancelled": EventSpec(levels=_U, frontend_emittable=True),
    "visit.revisit_required": EventSpec(levels=_U_S),
    "chemical_reading.logged": EventSpec(levels=_U_A, frontend_emittable=True),
    "chemistry.reading.out_of_range": EventSpec(levels=frozenset({"agent_action", "system_action"})),
    "chemistry.dose.applied": EventSpec(levels=_U, frontend_emittable=True),
    "chemistry.dose.expected_vs_actual": EventSpec(levels=_S),
    "photo.uploaded": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.8 Customers / Properties / Equipment ---
    "customer.created": EventSpec(levels=_U_S_A, frontend_emittable=True),
    "customer.edited": EventSpec(levels=_U, frontend_emittable=True),
    "customer.status_changed": EventSpec(levels=_U, frontend_emittable=True),
    "customer.cancelled": EventSpec(levels=_U, frontend_emittable=True),
    "customer.recurring_service_paused": EventSpec(levels=_U, frontend_emittable=True),
    "customer.recurring_service_resumed": EventSpec(levels=_U, frontend_emittable=True),
    "customer.recurring_service_skipped": EventSpec(levels=_U, frontend_emittable=True),
    "customer_contact.created": EventSpec(levels=_U, frontend_emittable=True),
    "customer_contact.edited": EventSpec(levels=_U, frontend_emittable=True),
    "property.created": EventSpec(levels=_U, frontend_emittable=True),
    "property.edited": EventSpec(levels=_U, frontend_emittable=True),
    "water_feature.created": EventSpec(levels=_U, frontend_emittable=True),
    "water_feature.edited": EventSpec(levels=_U, frontend_emittable=True),
    "equipment_item.added": EventSpec(levels=_U_A, frontend_emittable=True),
    "equipment_item.removed": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.9 Auth / Users ---
    "user.login": EventSpec(levels=_U, requires_org=False),
    "user.login_failed": EventSpec(levels=_E, requires_org=False),
    "user.logout": EventSpec(levels=_U, frontend_emittable=True, requires_org=False),
    "user.session_expired": EventSpec(levels=_S, requires_org=False),
    "user.password_reset_requested": EventSpec(levels=_U, requires_org=False),
    "user.password_reset_completed": EventSpec(levels=_U, requires_org=False),
    "user.email_recovered": EventSpec(levels=_U, requires_org=False),
    "user.invited": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.10 Settings / Config ---
    "settings.changed": EventSpec(levels=_U, frontend_emittable=True),
    "feature_flag.toggled": EventSpec(levels=_U, frontend_emittable=True),
    "workflow_config.changed": EventSpec(levels=_U, frontend_emittable=True),

    # --- 8.11 Navigation ---
    "page.viewed": EventSpec(levels=_U, frontend_emittable=True, requires_org=False),
    "page.exited": EventSpec(levels=_U, frontend_emittable=True, requires_org=False),

    # --- 8.12 Errors ---
    "error.backend_5xx": EventSpec(levels=_E, requires_org=False),
    "error.ai_call_failed": EventSpec(levels=_E),
    "error.email_send_failed": EventSpec(levels=_E),
    "error.background_job_failed": EventSpec(levels=_E, requires_org=False),
    "error.external_api_failed": EventSpec(levels=_E),
    "error.frontend_unhandled": EventSpec(levels=_E, frontend_emittable=True, requires_org=False),
    "platform_event.oversized_payload": EventSpec(levels=_E),

    # --- 8.13 Activation funnel ---
    "activation.account_created": EventSpec(levels=_U),
    "activation.first_customer_added": EventSpec(levels=_U),
    "activation.first_visit_completed": EventSpec(levels=_U),
    "activation.first_invoice_sent": EventSpec(levels=_U),
    "activation.first_payment_received": EventSpec(levels=_U_S),
    "activation.first_ai_proposal_accepted": EventSpec(levels=_U, frontend_emittable=True),

    # --- Meta / system ---
    "system.retention_purge.completed": EventSpec(levels=_S, requires_org=False),
    "system.partition.created": EventSpec(levels=_S, requires_org=False),
}


def is_known_event(event_type: str) -> bool:
    return event_type in EVENT_CATALOG


def spec_for(event_type: str) -> EventSpec | None:
    return EVENT_CATALOG.get(event_type)


def is_frontend_emittable(event_type: str) -> bool:
    spec = EVENT_CATALOG.get(event_type)
    return bool(spec and spec.frontend_emittable)
