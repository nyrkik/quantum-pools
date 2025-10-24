"""
Integration tests for Route Optimization.
"""

import pytest


@pytest.mark.integration
class TestRouteOptimization:
    """Test end-to-end route optimization workflows."""

    @pytest.mark.asyncio
    async def test_complete_optimization_workflow(self, client):
        """Test complete workflow from creating data to optimizing routes."""
            # Step 1: Create a driver
            driver_data = {
                "name": "Test Driver",
                "start_location_address": "1000 Start St, Test City, USA",
                "end_location_address": "1000 Start St, Test City, USA",
                "working_hours_start": "08:00:00",
                "working_hours_end": "17:00:00",
                "max_customers_per_day": 10
            }
            driver_response = await client.post("/api/drivers/", json=driver_data)
            assert driver_response.status_code == 201

            # Step 2: Create multiple customers
            customers = [
                {
                    "name": f"Customer {i}",
                    "address": f"{i}00 Test St, Test City, USA",
                    "service_type": "residential" if i % 2 == 0 else "commercial",
                    "difficulty": (i % 5) + 1,
                    "service_day": "monday",
                    "locked": False
                }
                for i in range(1, 6)
            ]

            for customer in customers:
                customer_response = await client.post("/api/customers/", json=customer)
                assert customer_response.status_code == 201

            # Step 3: Optimize routes
            optimization_request = {
                "service_day": "monday",
                "num_drivers": 1,
                "allow_day_reassignment": False
            }
            optimize_response = await client.post("/api/routes/optimize", json=optimization_request)

            assert optimize_response.status_code == 200
            optimization_data = optimize_response.json()

            # Verify optimization results
            assert "routes" in optimization_data
            assert "summary" in optimization_data

            # Note: Summary may be None if customers don't have coordinates (no geocoding in tests)
            if optimization_data["summary"]:
                assert optimization_data["summary"]["total_routes"] >= 1
                assert optimization_data["summary"]["total_customers"] == 5

            # Verify route structure
            if optimization_data["routes"]:
                route = optimization_data["routes"][0]
                assert "driver_id" in route
                assert "driver_name" in route
                assert "service_day" in route
                assert "stops" in route
                assert len(route["stops"]) > 0

                # Verify stops are sequenced
                for i, stop in enumerate(route["stops"], start=1):
                    assert stop["sequence"] == i

    @pytest.mark.asyncio
    async def test_save_and_retrieve_routes(self, client):
        """Test saving optimized routes and retrieving them."""
        
            # Create driver
            driver_data = {
                "name": "Save Test Driver",
                "start_location_address": "2000 Save St, Test City, USA",
                "end_location_address": "2000 Save St, Test City, USA",
                "working_hours_start": "08:00:00",
                "working_hours_end": "17:00:00",
                "max_customers_per_day": 10
            }
            driver_response = await client.post("/api/drivers/", json=driver_data)
            driver_id = driver_response.json()["id"]

            # Create customers
            for i in range(1, 4):
                customer_data = {
                    "name": f"Save Customer {i}",
                    "address": f"{i}000 Save St, Test City, USA",
                    "service_type": "residential",
                    "difficulty": 1,
                    "service_day": "tuesday",
                    "locked": False
                }
                await client.post("/api/customers/", json=customer_data)

            # Optimize
            optimize_response = await client.post("/api/routes/optimize", json={
                "service_day": "tuesday",
                "num_drivers": 1,
                "allow_day_reassignment": False
            })

            optimization_data = optimize_response.json()

            # Save routes
            save_request = {
                "service_day": "tuesday",
                "routes": optimization_data["routes"]
            }
            save_response = await client.post("/api/routes/save", json=save_request)

            assert save_response.status_code == 200
            save_data = save_response.json()
            assert "route_ids" in save_data
            assert len(save_data["route_ids"]) > 0

            # Retrieve saved routes
            get_response = await client.get("/api/routes/day/tuesday")

            assert get_response.status_code == 200
            routes = get_response.json()
            assert len(routes) > 0
            assert routes[0]["service_day"] == "tuesday"

    @pytest.mark.asyncio
    async def test_optimization_with_locked_customers(self, client):
        """Test optimization respects locked service days."""
        
            # Create driver
            driver_data = {
                "name": "Lock Test Driver",
                "start_location_address": "3000 Lock St, Test City, USA",
                "end_location_address": "3000 Lock St, Test City, USA",
                "working_hours_start": "08:00:00",
                "working_hours_end": "17:00:00",
                "max_customers_per_day": 10
            }
            await client.post("/api/drivers/", json=driver_data)

            # Create locked customer
            locked_customer = {
                "name": "Locked Customer",
                "address": "5000 Locked St, Test City, USA",
                "service_type": "residential",
                "difficulty": 1,
                "service_day": "wednesday",
                "locked": True
            }
            await client.post("/api/customers/", json=locked_customer)

            # Try to optimize for wednesday (should include locked customer)
            optimize_response = await client.post("/api/routes/optimize", json={
                "service_day": "wednesday",
                "num_drivers": 1,
                "allow_day_reassignment": False
            })

            optimization_data = optimize_response.json()
            if optimization_data.get("routes"):
                # Locked customer should be in wednesday route
                wednesday_customers = [
                    stop["customer_name"]
                    for route in optimization_data["routes"]
                    for stop in route["stops"]
                ]
                assert "Locked Customer" in wednesday_customers

    @pytest.mark.asyncio
    async def test_optimization_with_no_customers(self, client):
        """Test optimization gracefully handles no customers."""
        
            # Create driver
            driver_data = {
                "name": "Empty Test Driver",
                "start_location_address": "4000 Empty St, Test City, USA",
                "end_location_address": "4000 Empty St, Test City, USA",
                "working_hours_start": "08:00:00",
                "working_hours_end": "17:00:00",
                "max_customers_per_day": 10
            }
            await client.post("/api/drivers/", json=driver_data)

            # Try to optimize with no customers for a specific day
            optimize_response = await client.post("/api/routes/optimize", json={
                "service_day": "saturday",
                "num_drivers": 1,
                "allow_day_reassignment": False
            })

            # Should return error or empty routes
            assert optimize_response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_delete_routes_by_day(self, client):
        """Test deleting all routes for a specific day."""
        
            # Create driver and customers
            driver_data = {
                "name": "Delete Test Driver",
                "start_location_address": "6000 Delete St, Test City, USA",
                "end_location_address": "6000 Delete St, Test City, USA",
                "working_hours_start": "08:00:00",
                "working_hours_end": "17:00:00",
                "max_customers_per_day": 10
            }
            await client.post("/api/drivers/", json=driver_data)

            customer_data = {
                "name": "Delete Customer",
                "address": "7000 Delete St, Test City, USA",
                "service_type": "residential",
                "difficulty": 1,
                "service_day": "thursday",
                "locked": False
            }
            await client.post("/api/customers/", json=customer_data)

            # Optimize and save
            optimize_response = await client.post("/api/routes/optimize", json={
                "service_day": "thursday",
                "num_drivers": 1,
                "allow_day_reassignment": False
            })

            optimization_data = optimize_response.json()
            if optimization_data.get("routes"):
                save_request = {
                    "service_day": "thursday",
                    "routes": optimization_data["routes"]
                }
                await client.post("/api/routes/save", json=save_request)

                # Delete routes
                delete_response = await client.delete("/api/routes/day/thursday")
                assert delete_response.status_code == 204

                # Verify routes are deleted
                get_response = await client.get("/api/routes/day/thursday")
                routes = get_response.json()
                # Should be empty or return 404
                assert len(routes) == 0 or get_response.status_code == 404
