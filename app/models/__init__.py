"""
Database models package.
Import all models here so Alembic can auto-detect them.
"""

from app.models.organization import Organization
from app.models.user import User
from app.models.organization_user import OrganizationUser
from app.models.customer import Customer
from app.models.tech import Tech
from app.models.route import Route, RouteStop
from app.models.temp_assignment import TempTechAssignment
from app.models.tech_route import TechRoute

__all__ = [
    "Organization",
    "User",
    "OrganizationUser",
    "Customer",
    "Tech",
    "Route",
    "RouteStop",
    "TempTechAssignment",
    "TechRoute",
]
