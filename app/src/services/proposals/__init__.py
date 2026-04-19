"""Proposals subsystem — staged AI outputs awaiting human resolution.

Phase 2 primitive. Every AI suggestion flows through `ProposalService`
(stage → accept/edit/reject → entity creation + learning record).

See `docs/ai-platform-phase-2.md` for the full design.
"""
