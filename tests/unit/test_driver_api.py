"""
Unit tests for Driver API endpoints.
"""

import pytest


@pytest.mark.unit
class TestDriverAPI:
    """Test driver CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_driver(self, client):
        """Test creating a new driver."""
        driver_data = {
            "name": "John Doe",
            "start_location_address": "100 Start St, City, USA",
            "end_location_address": "100 Start St, City, USA",
            "working_hours_start": "08:00:00",
            "working_hours_end": "17:00:00",
            "max_customers_per_day": 20
        }

        response = await client.post("/api/drivers/", json=driver_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == driver_data["name"]
        assert "id" in data
        assert data["working_hours_start"] == "08:00:00"

    @pytest.mark.asyncio
    async def test_list_drivers(self, client):
        """Test listing drivers."""
        response = await client.get("/api/drivers/")

        assert response.status_code == 200
        data = response.json()
        assert "drivers" in data
        assert isinstance(data["drivers"], list)

    @pytest.mark.asyncio
    async def test_get_driver_by_id(self, client):
        """Test getting a specific driver by ID."""
        # Create a driver
        driver_data = {
            "name": "Jane Smith",
            "start_location_address": "200 Home St, City, USA",
            "end_location_address": "200 Home St, City, USA",
            "working_hours_start": "07:00:00",
            "working_hours_end": "16:00:00",
            "max_customers_per_day": 25
        }
        create_response = await client.post("/api/drivers/", json=driver_data)
        driver_id = create_response.json()["id"]

        # Get the driver by ID
        response = await client.get(f"/api/drivers/{driver_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == driver_id
        assert data["name"] == driver_data["name"]

    @pytest.mark.asyncio
    async def test_update_driver(self, client):
        """Test updating driver information."""
        # Create a driver
        driver_data = {
            "name": "Bob Johnson",
            "start_location_address": "300 Original St, City, USA",
            "end_location_address": "300 Original St, City, USA",
            "working_hours_start": "08:00:00",
            "working_hours_end": "17:00:00",
            "max_customers_per_day": 20
        }
        create_response = await client.post("/api/drivers/", json=driver_data)
        driver_id = create_response.json()["id"]

        # Update the driver
        update_data = {
            "name": "Bob Johnson Updated",
            "start_location_address": "400 Updated St, City, USA",
            "end_location_address": "400 Updated St, City, USA",
            "working_hours_start": "07:30:00",
            "working_hours_end": "16:30:00",
            "max_customers_per_day": 30
        }
        response = await client.put(f"/api/drivers/{driver_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Bob Johnson Updated"
        assert data["max_customers_per_day"] == 30

    @pytest.mark.asyncio
    async def test_delete_driver(self, client):
        """Test deleting a driver."""
        # Create a driver
        driver_data = {
            "name": "Temp Driver",
            "start_location_address": "500 Temp St, City, USA",
            "end_location_address": "500 Temp St, City, USA",
            "working_hours_start": "08:00:00",
            "working_hours_end": "17:00:00",
            "max_customers_per_day": 15
        }
        create_response = await client.post("/api/drivers/", json=driver_data)
        driver_id = create_response.json()["id"]

        # Delete the driver
        response = await client.delete(f"/api/drivers/{driver_id}")

        assert response.status_code == 204

        # Verify driver is deleted
        get_response = await client.get(f"/api/drivers/{driver_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_driver_working_hours_validation(self, client):
        """Test that working hours are validated properly."""
        # Valid working hours
        driver_data = {
            "name": "Test Driver",
            "start_location_address": "600 Test St, City, USA",
            "end_location_address": "600 Test St, City, USA",
            "working_hours_start": "08:00:00",
            "working_hours_end": "17:00:00",
            "max_customers_per_day": 20
        }

        response = await client.post("/api/drivers/", json=driver_data)
        assert response.status_code == 201
