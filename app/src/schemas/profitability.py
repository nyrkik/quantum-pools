"""Profitability analysis schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Org Cost Settings ---

class OrgCostSettingsUpdate(BaseModel):
    burdened_labor_rate: Optional[float] = None
    vehicle_cost_per_mile: Optional[float] = None
    chemical_cost_per_gallon: Optional[float] = None
    monthly_overhead: Optional[float] = None
    target_margin_pct: Optional[float] = Field(None, ge=0, le=100)
    residential_overhead_per_account: Optional[float] = None
    commercial_overhead_per_account: Optional[float] = None
    avg_drive_minutes: Optional[float] = None
    avg_drive_miles: Optional[float] = None
    visits_per_month: Optional[float] = None
    semi_annual_discount_type: Optional[str] = None
    semi_annual_discount_value: Optional[float] = None
    annual_discount_type: Optional[str] = None
    annual_discount_value: Optional[float] = None


class OrgCostSettingsResponse(BaseModel):
    id: str
    organization_id: str
    burdened_labor_rate: float
    vehicle_cost_per_mile: float
    chemical_cost_per_gallon: float
    monthly_overhead: float
    target_margin_pct: float
    residential_overhead_per_account: float = 10.0
    commercial_overhead_per_account: float = 45.0
    avg_drive_minutes: float = 5.0
    avg_drive_miles: float = 2.0
    visits_per_month: float = 4.0
    semi_annual_discount_type: str = "percent"
    semi_annual_discount_value: float = 5.0
    annual_discount_type: str = "percent"
    annual_discount_value: float = 10.0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Property Difficulty ---

class PropertyDifficultyUpdate(BaseModel):
    shallow_sqft: Optional[float] = None
    deep_sqft: Optional[float] = None
    has_deep_end: Optional[bool] = None
    spa_sqft: Optional[float] = None
    diving_board_count: Optional[int] = None
    pump_flow_gpm: Optional[float] = None
    is_indoor: Optional[bool] = None
    equipment_age_years: Optional[int] = None
    shade_exposure: Optional[str] = None
    tree_debris_level: Optional[str] = None
    enclosure_type: Optional[str] = None
    chem_feeder_type: Optional[str] = None
    access_difficulty_score: Optional[float] = Field(None, ge=1, le=5)
    customer_demands_score: Optional[float] = Field(None, ge=1, le=5)
    chemical_demand_score: Optional[float] = Field(None, ge=1, le=5)
    callback_frequency_score: Optional[float] = Field(None, ge=1, le=5)
    override_composite: Optional[float] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


class PropertyDifficultyResponse(BaseModel):
    id: str
    property_id: str
    shallow_sqft: Optional[float] = None
    deep_sqft: Optional[float] = None
    has_deep_end: bool
    spa_sqft: Optional[float] = None
    diving_board_count: int
    pump_flow_gpm: Optional[float] = None
    is_indoor: bool
    equipment_age_years: Optional[int] = None
    shade_exposure: Optional[str] = None
    tree_debris_level: Optional[str] = None
    enclosure_type: Optional[str] = None
    chem_feeder_type: Optional[str] = None
    access_difficulty_score: float
    customer_demands_score: float
    chemical_demand_score: float
    callback_frequency_score: float
    override_composite: Optional[float] = None
    notes: Optional[str] = None
    composite_score: float = 0.0
    difficulty_multiplier: float = 1.0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Bather Load ---

class JurisdictionResponse(BaseModel):
    id: str
    name: str
    method_key: str
    shallow_sqft_per_bather: float
    deep_sqft_per_bather: float
    spa_sqft_per_bather: float
    depth_based: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class BatherLoadRequest(BaseModel):
    pool_sqft: Optional[float] = None
    pool_gallons: Optional[int] = None
    shallow_sqft: Optional[float] = None
    deep_sqft: Optional[float] = None
    has_deep_end: bool = False
    spa_sqft: Optional[float] = None
    diving_board_count: int = 0
    pump_flow_gpm: Optional[float] = None
    is_indoor: bool = False
    jurisdiction_id: Optional[str] = None


class BatherLoadResult(BaseModel):
    max_bathers: int
    pool_bathers: int
    spa_bathers: int
    diving_bathers: int
    deck_bonus_bathers: int = 0
    flow_rate_bathers: Optional[int] = None
    jurisdiction_name: str
    method_key: str
    estimated_fields: list[str] = []
    pool_sqft_used: float
    shallow_sqft_used: float
    deep_sqft_used: float


# --- Profitability ---

class CostBreakdown(BaseModel):
    chemical_cost: float
    labor_cost: float
    travel_cost: float
    overhead_cost: float
    total_cost: float
    revenue: float
    profit: float
    margin_pct: float
    suggested_rate: float
    rate_gap: float


class ProfitabilityAccount(BaseModel):
    customer_id: str
    customer_name: str
    property_id: str
    property_address: str
    monthly_rate: float
    pool_gallons: Optional[int] = None
    pool_sqft: Optional[float] = None
    estimated_service_minutes: int
    difficulty_score: float
    difficulty_multiplier: float
    cost_breakdown: CostBreakdown
    margin_pct: float
    rate_per_gallon: Optional[float] = None


class PortfolioMedians(BaseModel):
    rate_per_gallon: float | None = None
    cost: float = 0
    margin_pct: float = 0
    difficulty: float = 0


class ProfitabilityOverview(BaseModel):
    total_accounts: int
    total_revenue: float
    total_cost: float
    total_profit: float
    avg_margin_pct: float
    below_target_count: int
    target_margin_pct: float
    accounts: list[ProfitabilityAccount]


class WhaleCurvePoint(BaseModel):
    rank: int
    customer_name: str
    customer_id: str
    cumulative_profit_pct: float
    individual_profit: float


class PricingSuggestion(BaseModel):
    customer_id: str
    customer_name: str
    property_address: str
    current_rate: float
    suggested_rate: float
    rate_gap: float
    current_margin_pct: float
    target_margin_pct: float
    difficulty_score: float


class BulkJurisdictionRequest(BaseModel):
    jurisdiction_id: str
    city: Optional[str] = None
    zip_code: Optional[str] = None
    state: Optional[str] = None
