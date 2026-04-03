"""Backward-compat alias — EMDInspection was renamed to Inspection."""
from src.models.inspection import Inspection as EMDInspection

__all__ = ["EMDInspection"]
