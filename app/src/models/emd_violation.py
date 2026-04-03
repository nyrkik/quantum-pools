"""Backward-compat alias — EMDViolation was renamed to InspectionViolation."""
from src.models.inspection_violation import InspectionViolation as EMDViolation

__all__ = ["EMDViolation"]
