"""API router — mounts all versioned route modules."""

from fastapi import APIRouter
from src.api.v1.auth import router as auth_router
from src.api.v1.customers import router as customers_router
from src.api.v1.properties import router as properties_router
from src.api.v1.techs import router as techs_router
from src.api.v1.visits import router as visits_router
from src.api.v1.routes import router as routes_router
from src.api.v1.invoices import router as invoices_router
from src.api.v1.payments import router as payments_router
from src.api.v1.profitability import router as profitability_router
from src.api.v1.satellite import router as satellite_router
from src.api.v1.water_features import router as water_features_router
from src.api.v1.photos import router as photos_router
from src.api.v1.team import router as team_router
from src.api.v1.dimensions import router as dimensions_router
from src.api.v1.chemical_costs import router as chemical_costs_router
from src.api.v1.inspection import router as inspection_router
from src.api.v1.billing import router as billing_router
from src.api.v1.service_tiers import router as service_tiers_router
from src.api.v1.notifications import router as notifications_router
from src.api.v1.branding import router as branding_router
from src.api.v1.agent_ops import router as agent_ops_router
from src.api.v1.permissions import router as permissions_router
from src.api.v1.admin_inspection import router as admin_inspection_router
from src.api.v1.admin_threads import router as admin_threads_router
from src.api.v1.admin_messages import router as admin_messages_router
from src.api.v1.admin_actions import router as admin_actions_router
from src.api.v1.admin_webhooks import router as admin_webhooks_router
from src.api.v1.charge_templates import router as charge_templates_router
from src.api.v1.visit_charges import router as visit_charges_router
from src.api.v1.charge_settings import router as charge_settings_router
from src.api.v1.email import router as email_router
from src.api.v1.service_checklist import router as service_checklist_router
from src.api.v1.vendors import router as vendors_router
from src.api.v1.part_purchases import router as part_purchases_router
from src.api.v1.parts import router as parts_router
from src.api.v1.equipment import router as equipment_router
from src.api.v1.equipment_catalog import router as equipment_catalog_router
from src.api.v1.inbox_routing import router as inbox_routing_router
from src.api.v1.inbound_email import router as inbound_email_router
from src.api.v1.public import router as public_router
from src.api.v1.feedback import router as feedback_router
from src.api.v1.messages import router as messages_router
from src.api.v1.customer_contacts import router as customer_contacts_router
from src.api.v1.attachments import router as attachments_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(customers_router)
api_router.include_router(properties_router)
api_router.include_router(techs_router)
api_router.include_router(visits_router)
api_router.include_router(routes_router)
api_router.include_router(invoices_router)
api_router.include_router(payments_router)
api_router.include_router(profitability_router)
api_router.include_router(satellite_router)
api_router.include_router(water_features_router)
api_router.include_router(photos_router)
api_router.include_router(team_router)
api_router.include_router(dimensions_router)
api_router.include_router(chemical_costs_router)
api_router.include_router(inspection_router)
api_router.include_router(billing_router)
api_router.include_router(service_tiers_router)
api_router.include_router(notifications_router)
api_router.include_router(branding_router)
api_router.include_router(agent_ops_router)
api_router.include_router(permissions_router)
api_router.include_router(admin_inspection_router)
api_router.include_router(admin_threads_router)
api_router.include_router(admin_messages_router)
api_router.include_router(admin_actions_router)
api_router.include_router(admin_webhooks_router)
api_router.include_router(charge_templates_router)
api_router.include_router(visit_charges_router)
api_router.include_router(charge_settings_router)
api_router.include_router(email_router)
api_router.include_router(service_checklist_router)
api_router.include_router(vendors_router)
api_router.include_router(part_purchases_router)
api_router.include_router(parts_router)
api_router.include_router(equipment_router)
api_router.include_router(equipment_catalog_router)
api_router.include_router(inbox_routing_router)
api_router.include_router(inbound_email_router)
api_router.include_router(public_router)
api_router.include_router(feedback_router)
api_router.include_router(messages_router)
api_router.include_router(customer_contacts_router)
api_router.include_router(attachments_router)
