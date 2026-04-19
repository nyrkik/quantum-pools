"""Proposals subsystem — staged AI outputs awaiting human resolution.

Phase 2 primitive. Every AI suggestion flows through `ProposalService`
(stage → accept/edit/reject → entity creation + learning record).

See `docs/ai-platform-phase-2.md` for the full design.
"""

# Populate the registry on first import. Each creator module
# registers itself at import time via the `@register` decorator.
from . import creators  # noqa: F401
from .proposal_service import ProposalService  # noqa: F401

__all__ = ["ProposalService"]
