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

    @pytest.mark.asyncio
    async def test_get_customer_by_id(self):
        """Test getting a specific customer by ID."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # First create a customer
            customer_data = {
                "name": "Test Pool",
                "address": "456 Oak St, Testtown, USA",
                "service_type": "commercial",
                "difficulty": 3,
                "service_day": "tuesday",
                "locked": True
            }
            create_response = await client.post("/api/customers/", json=customer_data)
            customer_id = create_response.json()["id"]

            # Get the customer by ID
            response = await client.get(f"/api/customers/{customer_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == customer_id
            assert data["name"] == customer_data["name"]
            assert data["locked"] is True

    @pytest.mark.asyncio
    async def test_update_customer(self):
        """Test updating customer information."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Create a customer
            customer_data = {
                "name": "Original Pool",
                "address": "789 Pine St, Original, USA",
                "service_type": "residential",
                "difficulty": 1,
                "service_day": "wednesday",
                "locked": False
            }
            create_response = await client.post("/api/customers/", json=customer_data)
            customer_id = create_response.json()["id"]

            # Update the customer
            update_data = {
                "name": "Updated Pool",
                "address": "789 Pine St, Updated, USA",
                "service_type": "commercial",
                "difficulty": 4,
                "service_day": "thursday",
                "locked": True
            }
            response = await client.put(f"/api/customers/{customer_id}", json=update_data)

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated Pool"
            assert data["difficulty"] == 4
            assert data["service_day"] == "thursday"

    @pytest.mark.asyncio
    async def test_delete_customer(self):
        """Test deleting a customer."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Create a customer
            customer_data = {
                "name": "Temp Pool",
                "address": "999 Delete St, Temp, USA",
                "service_type": "residential",
                "difficulty": 1,
                "service_day": "friday",
                "locked": False
            }
            create_response = await client.post("/api/customers/", json=customer_data)
            customer_id = create_response.json()["id"]

            # Delete the customer
            response = await client.delete(f"/api/customers/{customer_id}")

            assert response.status_code == 204

            # Verify customer is deleted
            get_response = await client.get(f"/api/customers/{customer_id}")
            assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_filter_customers_by_service_day(self):
        """Test filtering customers by service day."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Create customers for different days
            monday_customer = {
                "name": "Monday Pool",
                "address": "111 Monday St",
                "service_type": "residential",
                "difficulty": 1,
                "service_day": "monday",
                "locked": False
            }
            tuesday_customer = {
                "name": "Tuesday Pool",
                "address": "222 Tuesday St",
                "service_type": "residential",
                "difficulty": 1,
                "service_day": "tuesday",
                "locked": False
            }

            await client.post("/api/customers/", json=monday_customer)
            await client.post("/api/customers/", json=tuesday_customer)

            # Filter by monday
            response = await client.get("/api/customers/?service_day=monday")

            assert response.status_code == 200
            data = response.json()
            # Note: may have other customers from other tests
            assert any(c["service_day"] == "monday" for c in data["customers"])
