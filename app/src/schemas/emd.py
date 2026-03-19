"""EMD inspection schemas — request/response models for EMD endpoints."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date


# --- Facility ---

class EMDFacilityResponse(BaseModel):
    id: str
    organization_id: Optional[str] = None
    name: str
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: str = "CA"
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    facility_id: Optional[str] = None
    permit_holder: Optional[str] = None
    facility_type: Optional[str] = None
    program_identifier: Optional[str] = None
    matched_property_id: Optional[str] = None
    matched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EMDFacilityListResponse(BaseModel):
    id: str
    name: str
    street_address: Optional[str] = None
    city: Optional[str] = None
    facility_id: Optional[str] = None
    facility_type: Optional[str] = None
    program_identifier: Optional[str] = None
    permit_id: Optional[str] = None
    matched_property_id: Optional[str] = None
    total_inspections: int = 0
    total_violations: int = 0
    last_inspection_date: Optional[date] = None
    is_closed: bool = False
    closure_reasons: list[str] = []

    model_config = {"from_attributes": True}


class EMDFacilityDetailResponse(EMDFacilityResponse):
    inspections: list["EMDInspectionDetailResponse"] = []
    total_inspections: int = 0
    total_violations: int = 0
    last_inspection_date: Optional[date] = None
    matched_property_address: Optional[str] = None
    matched_customer_name: Optional[str] = None


# --- Inspection ---

class EMDInspectionResponse(BaseModel):
    id: str
    facility_id: str
    inspection_id: Optional[str] = None
    inspection_date: Optional[date] = None
    inspection_type: Optional[str] = None
    inspector_name: Optional[str] = None
    program_identifier: Optional[str] = None
    permit_id: Optional[str] = None
    total_violations: int = 0
    major_violations: int = 0
    pool_capacity_gallons: Optional[int] = None
    flow_rate_gpm: Optional[int] = None
    pdf_path: Optional[str] = None
    report_notes: Optional[str] = None
    closure_status: Optional[str] = None
    closure_required: bool = False
    reinspection_required: bool = False
    water_chemistry: Optional[dict] = None
    has_pdf: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class EMDInspectionDetailResponse(EMDInspectionResponse):
    violations: list["EMDViolationResponse"] = []
    equipment: Optional["EMDEquipmentResponse"] = None


# --- Violation ---

class EMDViolationResponse(BaseModel):
    id: str
    inspection_id: str
    facility_id: str
    violation_code: Optional[str] = None
    violation_title: Optional[str] = None
    observations: Optional[str] = None
    corrective_action: Optional[str] = None
    is_major_violation: bool = False
    severity_level: Optional[str] = None
    shorthand_summary: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Equipment ---

class EMDEquipmentResponse(BaseModel):
    id: str
    inspection_id: str
    facility_id: str
    pool_capacity_gallons: Optional[int] = None
    flow_rate_gpm: Optional[int] = None
    filter_pump_1_make: Optional[str] = None
    filter_pump_1_model: Optional[str] = None
    filter_pump_1_hp: Optional[str] = None
    filter_pump_2_make: Optional[str] = None
    filter_pump_2_model: Optional[str] = None
    filter_pump_2_hp: Optional[str] = None
    filter_pump_3_make: Optional[str] = None
    filter_pump_3_model: Optional[str] = None
    filter_pump_3_hp: Optional[str] = None
    jet_pump_1_make: Optional[str] = None
    jet_pump_1_model: Optional[str] = None
    jet_pump_1_hp: Optional[str] = None
    filter_1_type: Optional[str] = None
    filter_1_make: Optional[str] = None
    filter_1_model: Optional[str] = None
    filter_1_capacity_gpm: Optional[int] = None
    sanitizer_1_type: Optional[str] = None
    sanitizer_1_details: Optional[str] = None
    sanitizer_2_type: Optional[str] = None
    sanitizer_2_details: Optional[str] = None
    main_drain_type: Optional[str] = None
    main_drain_model: Optional[str] = None
    main_drain_install_date: Optional[str] = None
    equalizer_model: Optional[str] = None
    equalizer_install_date: Optional[str] = None
    pump_notes: Optional[str] = None
    filter_notes: Optional[str] = None
    sanitizer_notes: Optional[str] = None
    main_drain_notes: Optional[str] = None
    equalizer_notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Requests ---

class ScrapeRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None  # defaults to start_date
    rate_limit_seconds: int = 5


class MatchFacilityRequest(BaseModel):
    property_id: str


# --- Lead generation ---

class EMDLeadResponse(BaseModel):
    facility_id: str
    facility_name: str
    street_address: Optional[str] = None
    city: Optional[str] = None
    total_inspections: int = 0
    total_violations: int = 0
    major_violations: int = 0
    last_inspection_date: Optional[date] = None
    is_matched: bool = False
    violation_trend: str = "stable"  # increasing, decreasing, stable


# Forward refs
EMDFacilityDetailResponse.model_rebuild()
EMDInspectionDetailResponse.model_rebuild()
