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
from src.api.v1.measurements import router as measurements_router

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
api_router.include_router(measurements_router)
