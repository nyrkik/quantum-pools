"""RFC 6902 JSON patch helper for `user_delta` computation.

When a user `edit_and_accept`s a proposal, we record the diff between
the original `proposed_payload` and the human-edited payload as an
RFC 6902 patch. Sonar and the learning loop consume this to see
*exactly what the human changed* — not just "user edited," but "user
changed `action_type` from 'bid' to 'repair' and bumped the due_date
forward by 2 days."

Why 6902 over shallow diff: the patch format is canonical, tooling
exists everywhere, and it handles nested edits + array ops cleanly.
`jsonpatch.make_patch` produces minimal patches.
"""

from __future__ import annotations

from typing import Any

import jsonpatch


def make_patch(original: dict[str, Any], edited: dict[str, Any]) -> list[dict]:
    """Return a minimal RFC 6902 patch from `original` to `edited`.

    Empty list when they're equal.
    """
    patch = jsonpatch.make_patch(original, edited)
    return list(patch)


def apply_patch(doc: dict[str, Any], patch: list[dict]) -> dict[str, Any]:
    """Apply `patch` to `doc` (non-destructive — returns a new dict).

    Useful in tests + for a future 'replay' feature that reconstructs a
    proposal from its original + stored user_delta.
    """
    return jsonpatch.apply_patch(doc, patch, in_place=False)
