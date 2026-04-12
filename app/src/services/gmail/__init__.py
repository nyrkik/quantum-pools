"""Gmail integration — OAuth, sync, outbound.

Phase 5b.2 of docs/email-integrations-plan.md. The customer connects their
Google Workspace account via OAuth, QP syncs inbound mail into AgentMessage
records, and outbound replies go via the Gmail API so they appear in the
user's Sent folder alongside their manually-sent emails.

Submodules:
    oauth      — Build authorize URLs, exchange codes, refresh tokens
    client     — Authenticated googleapiclient wrapper with token refresh
    sync       — Initial + incremental sync into AgentMessage records
    outbound   — Send replies via users.messages.send

The integration's OAuth tokens live in EmailIntegration.config_encrypted
(Fernet-encrypted via src.core.encryption).
"""
