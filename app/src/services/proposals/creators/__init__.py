"""Proposal creators — one module per entity_type.

Each module registers itself via `@register(...)` at import time.
Importing this package triggers registration for all creators.

Step 3 ships: job, estimate, equipment_item, org_config.
Later DeepBlue migration adds: broadcast_email, chemical_reading,
customer_note_update, and more.
"""

# Import side effect: each module's @register decorator populates
# src.services.proposals.registry._REGISTRY.
from . import job, estimate, equipment_item, org_config  # noqa: F401
from . import chemical_reading  # noqa: F401
from . import case  # noqa: F401
from . import customer_note_update  # noqa: F401
from . import broadcast_email  # noqa: F401
from . import customer_email  # noqa: F401
from . import case_link  # noqa: F401
from . import email_reply  # noqa: F401
from . import customer_match_suggestion  # noqa: F401
from . import workflow_config  # noqa: F401
from . import inbox_rule  # noqa: F401
