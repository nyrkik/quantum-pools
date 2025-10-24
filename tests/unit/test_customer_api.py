"""
Unit tests for Customer API endpoints.
"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.unit
class TestCustomerAPI:
    """Test customer CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_customer(self):
        """Test creating a new customer."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            customer_data = {
                "name": "John's Pool Service",
                "address": "123 Main St, Anytown, USA",
                "service_type": "residential",
                "difficulty": 2,
                "service_day": "monday",
                "locked": False
            }

            response = await client.post("/api/customers/", json=customer_data)

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == customer_data["name"]
            assert data["address"] == customer_data["address"]
            assert "id" in data
            assert "created_at" in data

    @pytest.mark.asyncio
    async def test_list_customers(self):
        """Test listing customers with pagination."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/customers/")

            assert response.status_code == 200
            data = response.json()
            assert "customers" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
