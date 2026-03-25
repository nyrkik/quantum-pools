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
from src.api.v1.emd import router as emd_router
from src.api.v1.billing import router as billing_router
from src.api.v1.service_tiers import router as service_tiers_router
from src.api.v1.notifications import router as notifications_router
from src.api.v1.branding import router as branding_router
from src.api.v1.agent_ops import router as agent_ops_router
from src.api.v1.permissions import router as permissions_router
from src.api.v1.admin_emd import router as admin_emd_router
from src.api.v1.admin_threads import router as admin_threads_router
from src.api.v1.admin_messages import router as admin_messages_router
from src.api.v1.admin_actions import router as admin_actions_router
from src.api.v1.admin_webhooks import router as admin_webhooks_router
from src.api.v1.email import router as email_router

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
api_router.include_router(emd_router)
api_router.include_router(billing_router)
api_router.include_router(service_tiers_router)
api_router.include_router(notifications_router)
api_router.include_router(branding_router)
api_router.include_router(agent_ops_router)
api_router.include_router(permissions_router)
api_router.include_router(admin_emd_router)
api_router.include_router(admin_threads_router)
api_router.include_router(admin_messages_router)
api_router.include_router(admin_actions_router)
api_router.include_router(admin_webhooks_router)
api_router.include_router(email_router)
