"""
SQLAlchemy ORM models.
Import all models here so Alembic can discover them.
"""

from src.core.database import Base
from src.models.organization import Organization
from src.models.user import User
from src.models.organization_user import OrganizationUser
from src.models.user_session import UserSession
from src.models.customer import Customer
from src.models.property import Property
from src.models.tech import Tech
from src.models.service import Service
from src.models.visit import Visit
from src.models.visit_service import VisitService
from src.models.chemical_reading import ChemicalReading
from src.models.geocode_cache import GeocodeCache
from src.models.route import Route, RouteStop, TempTechAssignment
from src.models.invoice import Invoice, InvoiceLineItem, InvoiceRevision
from src.models.payment import Payment
from src.models.org_cost_settings import OrgCostSettings
from src.models.property_difficulty import PropertyDifficulty
from src.models.bather_load_jurisdiction import BatherLoadJurisdiction
from src.models.property_jurisdiction import PropertyJurisdiction
from src.models.satellite_analysis import SatelliteAnalysis
from src.models.pool_measurement import PoolMeasurement
from src.models.water_feature import WaterFeature
from src.models.property_photo import PropertyPhoto
from src.models.dimension_estimate import DimensionEstimate
from src.models.regional_default import RegionalDefault
from src.models.org_chemical_prices import OrgChemicalPrices
from src.models.chemical_cost_profile import ChemicalCostProfile
from src.models.inspection_facility import InspectionFacility
from src.models.inspection import Inspection
from src.models.inspection_violation import InspectionViolation
from src.models.inspection_equipment import InspectionEquipment
from src.models.service_tier import ServiceTier
from src.models.feature import Feature, FeatureTier
from src.models.org_subscription import OrgSubscription
from src.models.inspection_lookup import InspectionLookup
from src.models.scraper_run import ScraperRun
from src.models.estimate_approval import EstimateApproval
from src.models.inbox_routing_rule import InboxRoutingRule
from src.models.agent_thread import AgentThread
from src.models.agent_message import AgentMessage
from src.models.agent_action import AgentAction, AgentActionComment
from src.models.agent_action_task import AgentActionTask
from src.services.agents.observability import AgentLog
from src.services.agents.evals import AgentEvalCase, AgentEvalResult
from src.models.charge_template import ChargeTemplate
from src.models.visit_charge import VisitCharge
from src.models.visit_photo import VisitPhoto
from src.models.service_checklist_item import ServiceChecklistItem
from src.models.visit_checklist_entry import VisitChecklistEntry
from src.models.notification import Notification
from src.models.permission import Permission
from src.models.permission_preset import PermissionPreset
from src.models.preset_permission import PresetPermission
from src.models.org_role import OrgRole
from src.models.org_role_permission import OrgRolePermission
from src.models.user_permission_override import UserPermissionOverride
from src.models.vendor import Vendor
from src.models.parts_catalog import PartsCatalog
from src.models.part_purchase import PartPurchase
from src.models.equipment_catalog import EquipmentCatalog
from src.models.equipment_item import EquipmentItem
from src.models.equipment_event import EquipmentEvent
from src.models.feedback_item import FeedbackItem
from src.models.property_access_code import PropertyAccessCode
from src.models.internal_message import InternalThread, InternalMessage
from src.models.customer_contact import CustomerContact
from src.models.agent_correction import AgentCorrection
from src.models.thread_read import ThreadRead
from src.models.job_invoice import JobInvoice

__all__ = [
    "Base",
    "Organization",
    "User",
    "OrganizationUser",
    "UserSession",
    "Customer",
    "Property",
    "Tech",
    "Service",
    "Visit",
    "VisitService",
    "ChemicalReading",
    "GeocodeCache",
    "Route",
    "RouteStop",
    "TempTechAssignment",
    "Invoice",
    "InvoiceLineItem",
    "InvoiceRevision",
    "Payment",
    "OrgCostSettings",
    "PropertyDifficulty",
    "BatherLoadJurisdiction",
    "PropertyJurisdiction",
    "SatelliteAnalysis",
    "PoolMeasurement",
    "WaterFeature",
    "PropertyPhoto",
    "DimensionEstimate",
    "RegionalDefault",
    "OrgChemicalPrices",
    "ChemicalCostProfile",
    "InspectionFacility",
    "Inspection",
    "InspectionViolation",
    "InspectionEquipment",
    "Feature",
    "FeatureTier",
    "OrgSubscription",
    "InspectionLookup",
    "ChargeTemplate",
    "VisitCharge",
    "VisitPhoto",
    "ServiceChecklistItem",
    "VisitChecklistEntry",
    "ServiceTier",
    "Vendor",
    "PartsCatalog",
    "PartPurchase",
    "EquipmentCatalog",
    "EquipmentItem",
    "EquipmentEvent",
    "InboxRoutingRule",
    "FeedbackItem",
    "PropertyAccessCode",
    "InternalThread",
    "InternalMessage",
    "CustomerContact",
    "AgentCorrection",
]
