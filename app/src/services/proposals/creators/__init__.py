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
