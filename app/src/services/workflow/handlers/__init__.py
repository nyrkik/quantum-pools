"""Concrete workflow handlers. Importing this package triggers
self-registration of every handler into `workflow.registry.HANDLERS`.
"""

# Each module self-registers via @register.
from src.services.workflow.handlers import (  # noqa: F401
    assign_inline,
    schedule_inline,
    hold_for_dispatch,
)
