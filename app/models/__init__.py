"""
Database models package.
Import all models here so Alembic can auto-detect them.
"""

from app.models.customer import Customer
from app.models.driver import Driver
from app.models.route import Route, RouteStop

__all__ = [
    "Customer",
    "Driver",
    "Route",
    "RouteStop",
]
