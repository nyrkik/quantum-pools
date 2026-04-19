"""Proposal creators — one module per entity_type.

Each module registers itself via `@register(...)` at import time.
This file imports them all so registration happens automatically
when the proposals package loads.

Step 3 adds: job, estimate, equipment_item, org_config.
Later DeepBlue migration adds: broadcast_email, chemical_reading,
customer_note_update, and more.
"""
