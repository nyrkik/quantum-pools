"""Chemical cost engine schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Regional Defaults ---

class RegionalDefaultResponse(BaseModel):
    id: str
    region_key: str
    sanitizer_type: str
    sanitizer_usage_oz: float
    acid_usage_oz: float
    sanitizer_price_per_unit: Optional[float] = None
    sanitizer_unit: Optional[str] = None
    acid_price_per_gallon: float
    cya_price_per_lb: float
    salt_price_per_bag: float
    cya_usage_lb_per_month_per_10k: float
    salt_bags_per_year_per_10k: float
    salt_cell_replacement_cost: float = 0
    insurance_chemicals_monthly: float = 0
    source: Optional[str] = None
    last_updated: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Org Chemical Prices ---

class OrgChemicalPricesUpdate(BaseModel):
    liquid_chlorine_per_gal: Optional[float] = Field(None, ge=0)
    tabs_per_bucket: Optional[float] = Field(None, ge=0)
    cal_hypo_per_lb: Optional[float] = Field(None, ge=0)
    dichlor_per_lb: Optional[float] = Field(None, ge=0)
    salt_per_bag: Optional[float] = Field(None, ge=0)
    acid_per_gal: Optional[float] = Field(None, ge=0)
    cya_per_lb: Optional[float] = Field(None, ge=0)
    bromine_per_lb: Optional[float] = Field(None, ge=0)


class OrgChemicalPricesResponse(BaseModel):
    id: str
    organization_id: str
    liquid_chlorine_per_gal: Optional[float] = None
    tabs_per_bucket: Optional[float] = None
    cal_hypo_per_lb: Optional[float] = None
    dichlor_per_lb: Optional[float] = None
    salt_per_bag: Optional[float] = None
    acid_per_gal: Optional[float] = None
    cya_per_lb: Optional[float] = None
    bromine_per_lb: Optional[float] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Chemical Cost Profile ---

class ChemicalCostProfileResponse(BaseModel):
    id: str
    body_of_water_id: str
    organization_id: str
    sanitizer_cost: float
    acid_cost: float
    cya_cost: float
    salt_cost: float
    cell_cost: float = 0
    insurance_cost: float = 0
    total_monthly: float
    source: str
    overrides: Optional[dict] = None
    adjustments_applied: Optional[dict] = None
    last_computed: Optional[datetime] = None
    sanitizer_usage_override_oz: Optional[float] = None
    acid_usage_override_oz: Optional[float] = None

    model_config = {"from_attributes": True}


class ChemicalCostProfileUpdate(BaseModel):
    """Allow user to override individual cost fields or usage rates."""
    sanitizer_cost: Optional[float] = Field(None, ge=0)
    acid_cost: Optional[float] = Field(None, ge=0)
    cya_cost: Optional[float] = Field(None, ge=0)
    salt_cost: Optional[float] = Field(None, ge=0)
    sanitizer_usage_override_oz: Optional[float] = Field(None, ge=0)
    acid_usage_override_oz: Optional[float] = Field(None, ge=0)
