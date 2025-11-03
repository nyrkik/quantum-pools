"""
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
import logging

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="QuantumPools",
    description="Pool service route optimization and scheduling system",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "0.1.0"
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - redirect to docs or serve frontend."""
    return {
        "message": "QuantumPools API",
        "docs": "/docs",
        "frontend": "/static/index.html"
    }


# Config endpoint for frontend
@app.get("/api/config")
async def get_config():
    """Get public configuration for frontend."""
    return {
        "google_maps_api_key": settings.google_maps_api_key or None,
        "has_google_maps": bool(settings.google_maps_api_key)
    }


# Geocode endpoint
@app.get("/api/geocode")
async def geocode_address(address: str):
    """
    Geocode an address to GPS coordinates.

    Args:
        address: Street address to geocode

    Returns:
        Dict with latitude and longitude, or error message
    """
    from app.services.geocoding import geocoding_service

    if not address:
        return {"error": "Address parameter is required"}

    try:
        result = await geocoding_service.geocode_address(address)

        if result:
            latitude, longitude = result
            return {
                "latitude": latitude,
                "longitude": longitude,
                "address": address
            }
        else:
            return {
                "error": "Could not geocode address",
                "address": address
            }
    except Exception as e:
        logger.error(f"Error geocoding address '{address}': {str(e)}")
        return {
            "error": f"Geocoding failed: {str(e)}",
            "address": address
        }


# Validate customer coordinates endpoint
@app.get("/api/customers/validate-coordinates")
async def validate_customer_coordinates():
    """
    Validate all customer coordinates against their addresses.

    Returns a list of customers with mismatched or invalid coordinates.
    """
    from app.services.geocoding import geocoding_service
    from app.database import get_db
    from app.models.customer import Customer
    from sqlalchemy import select
    import math

    async def calculate_distance(lat1, lon1, lat2, lon2):
        """Calculate distance in miles between two coordinates."""
        R = 3959  # Earth radius in miles
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    issues = []

    try:
        async for db in get_db():
            # Get all active customers
            result = await db.execute(select(Customer).where(Customer.is_active == True))
            customers = result.scalars().all()

            for customer in customers:
                issue = {
                    "id": str(customer.id),
                    "name": customer.name,
                    "address": customer.address,
                    "current_latitude": customer.latitude,
                    "current_longitude": customer.longitude,
                    "issues": []
                }

                # Check if coordinates are missing
                if not customer.latitude or not customer.longitude:
                    issue["issues"].append("Missing coordinates")
                    issue["severity"] = "high"
                    issues.append(issue)
                    continue

                # Check if coordinates are valid ranges
                if (customer.latitude < -90 or customer.latitude > 90 or
                    customer.longitude < -180 or customer.longitude > 180):
                    issue["issues"].append("Coordinates out of valid range")
                    issue["severity"] = "high"
                    issues.append(issue)
                    continue

                # Geocode the address to compare
                try:
                    geocoded = await geocoding_service.geocode_with_rate_limit(customer.address)

                    if geocoded:
                        correct_lat, correct_lon = geocoded
                        distance = await calculate_distance(
                            customer.latitude, customer.longitude,
                            correct_lat, correct_lon
                        )

                        # Flag if coordinates are more than 5 miles off
                        if distance > 5.0:
                            issue["issues"].append(f"Coordinates {distance:.1f} miles from address")
                            issue["correct_latitude"] = correct_lat
                            issue["correct_longitude"] = correct_lon
                            issue["distance_miles"] = round(distance, 2)
                            issue["severity"] = "high" if distance > 50 else "medium"
                            issues.append(issue)
                    else:
                        issue["issues"].append("Address could not be geocoded for validation")
                        issue["severity"] = "low"
                        issues.append(issue)

                except Exception as e:
                    logger.error(f"Error validating customer {customer.id}: {str(e)}")
                    issue["issues"].append(f"Validation error: {str(e)}")
                    issue["severity"] = "low"
                    issues.append(issue)

            break  # Exit the async generator loop

        return {
            "total_customers": len(customers),
            "issues_found": len(issues),
            "customers_with_issues": issues
        }

    except Exception as e:
        logger.error(f"Error validating coordinates: {str(e)}")
        return {
            "error": f"Validation failed: {str(e)}"
        }


# Import and include routers
from app.api import auth, customers, techs, routes, imports
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(techs.router)
app.include_router(routes.router)
app.include_router(imports.router)


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info(f"Starting QuantumPools in {settings.environment} mode")
    logger.info(f"Database: {settings.database_url.split('@')[-1]}")  # Don't log password


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down QuantumPools")
