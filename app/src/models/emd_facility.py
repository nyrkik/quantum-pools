"""Backward-compat alias — EMDFacility was renamed to InspectionFacility."""
from src.models.inspection_facility import InspectionFacility as EMDFacility

__all__ = ["EMDFacility"]
