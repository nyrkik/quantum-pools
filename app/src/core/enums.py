"""Centralized enum definitions shared across models.

Enums that are used by multiple models live here to prevent duplication
and ensure consistent values across the codebase.
"""

import enum


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    check = "check"
    credit_card = "credit_card"
    ach = "ach"
    stripe = "stripe"
    other = "other"
