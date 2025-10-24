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
    title="RouteOptimizer",
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
        "message": "RouteOptimizer API",
        "docs": "/docs",
        "frontend": "/static/index.html"
    }


# Import and include routers
from app.api import customers, drivers, routes, imports
app.include_router(customers.router)
app.include_router(drivers.router)
app.include_router(routes.router)
app.include_router(imports.router)


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info(f"Starting RouteOptimizer in {settings.environment} mode")
    logger.info(f"Database: {settings.database_url.split('@')[-1]}")  # Don't log password


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down RouteOptimizer")
