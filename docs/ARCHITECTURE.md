# Architecture Reference

**Last Updated:** 2025-10-25

## Tech Stack

- **Backend:** FastAPI (async), Python 3.11+
- **Database:** PostgreSQL (async SQLAlchemy 2.0)
- **Optimization:** Google OR-Tools VRP solver
- **Geocoding:** Geopy (OpenStreetMap Nominatim or Google Maps)
- **Frontend:** Vanilla JS + Leaflet.js maps
- **PDF Export:** ReportLab

## Database Schema

### Tables

**customers**
- `id` UUID (PK)
- `name`, `address` (strings)
- `latitude`, `longitude` (float, nullable)
- `assigned_driver_id` UUID (FK to drivers, nullable)
- `service_type` (residential | commercial)
- `difficulty` (1-5 scale)
- `service_day` (monday-sunday, primary day)
- `service_days_per_week` (1, 2, or 3)
- `service_schedule` (e.g., "Mo/Th", "Mo/We/Fr", nullable for 1x/week)
- `locked` (boolean - prevents day reassignment)
- `time_window_start`, `time_window_end` (time, nullable)
- `notes`, `is_active`, timestamps

**drivers**
- `id` UUID (PK)
- `name`, `email`, `phone`
- `color` (hex code for route visualization)
- `start_location_address`, `start_latitude`, `start_longitude`
- `end_location_address`, `end_latitude`, `end_longitude`
- `working_hours_start`, `working_hours_end` (time)
- `max_customers_per_day` (integer, default 20)
- `is_active`, `notes`, timestamps

**routes**
- `id` UUID (PK)
- `driver_id` UUID (FK to drivers, cascade delete)
- `service_day` (monday-sunday)
- `total_duration_minutes`, `total_distance_miles`, `total_customers`
- `optimization_algorithm` (default: google-or-tools)
- `optimization_score` (float, nullable)
- timestamps

**route_stops**
- `id` UUID (PK)
- `route_id` UUID (FK to routes, cascade delete)
- `customer_id` UUID (FK to customers, cascade delete)
- `sequence` (integer, 1-based order)
- `estimated_arrival_time`, `estimated_service_duration`
- `estimated_drive_time_from_previous`, `estimated_distance_from_previous`
- `created_at`

### Relationships

- Driver → Routes (one-to-many, cascade delete)
- Route → Stops (one-to-many, cascade delete)
- Customer → Stops (one-to-many, cascade delete)
- Customer → Driver (many-to-one via assigned_driver_id, nullable)

## API Endpoints

### Customers `/api/customers`
- `POST /` - Create customer (auto-geocodes address)
- `GET /` - List with pagination/filters (service_day, service_type, is_active)
- `GET /{id}` - Get single customer
- `PUT /{id}` - Update customer (full)
- `PATCH /{id}` - Update customer (partial)
- `DELETE /{id}` - Delete customer
- `GET /service-day/{day}` - Get customers for specific day

### Drivers `/api/drivers`
- `POST /` - Create driver (auto-geocodes locations)
- `GET /` - List with pagination/filters (is_active)
- `GET /active` - Get all active drivers
- `GET /{id}` - Get single driver
- `PUT /{id}` - Update driver
- `DELETE /{id}` - Delete driver

### Routes `/api/routes`
- `POST /optimize` - Generate optimized routes (doesn't save to DB)
- `POST /save` - Save optimized routes to database
- `GET /day/{service_day}` - Get saved routes for day
- `DELETE /day/{service_day}` - Delete all routes for day
- `GET /{route_id}` - Get route details with stops
- `GET /{route_id}/pdf` - Download PDF route sheet
- `GET /day/{service_day}/pdf` - Download PDF for all routes on day
- `PATCH /{route_id}/stops` - Update stop sequence
- `POST /{route_id}/stops/{stop_id}/move` - Move stop to different route

### Imports `/api/imports`
- `POST /customers/csv` - Bulk import customers from CSV
- `GET /customers/template` - Download CSV template

### Other
- `GET /api/geocode?address=...` - Geocode single address
- `GET /api/customers/validate-coordinates` - Validate all customer coords
- `GET /api/config` - Get frontend config (Google Maps key status)
- `GET /health` - Health check

## Optimization Service

**Location:** `app/services/optimization.py`

**Key Method:** `optimize_routes(customers, drivers, service_day, allow_day_reassignment, optimization_mode)`

**Modes:**
- `full` - Optimize all customers, can reassign drivers
- `refine` - Only customers with assigned_driver_id, keeps driver assignments

**Flow:**
1. Filter customers by day (if specified)
2. Build distance matrix (lat/lon → miles)
3. Calculate service durations (type + difficulty)
4. Configure OR-Tools VRP solver with constraints
5. Run optimization (120 second limit)
6. Parse solution into route data

**Constraints:**
- Driver working hours
- Max customers per driver
- Service time windows (if specified)
- Distance + service time limits

**Special Handling:**
- "All Days" without reassignment → optimize each day separately
- "All Days" with reassignment → not yet implemented (returns message)

## Geocoding Service

**Location:** `app/services/geocoding.py`

- Uses Geopy with Nominatim (OpenStreetMap) by default
- Falls back to Google Maps if API key configured
- Rate limiting for batch operations (`geocode_with_rate_limit`)
- Automatically geocodes on customer/driver create/update

## PDF Export Service

**Location:** `app/services/pdf_export.py`

- Single route sheets
- Multi-route daily packets
- Uses ReportLab for PDF generation

## Configuration

**File:** `app/config.py`

**Key Settings:**
- `database_url` - PostgreSQL connection
- `secret_key` - Session encryption
- `google_maps_api_key` - Optional geocoding
- `optimization_time_limit_seconds` - 120s default
- `max_customers_per_route` - 50 default
- `allowed_origins` - CORS config
- `log_level` - INFO default

## Frontend Structure

**Main File:** `static/index.html` + `static/js/app.js`

**Key Components:**
- Leaflet.js map with customer/route visualization
- Day selector tabs
- Driver/tech selector (sidebar, needs redesign)
- Optimization controls (mode, day reassignment)
- Customer management (CRUD, CSV import, coordinate validation)
- Driver management (CRUD)

**Map Features:**
- Color-coded routes by driver
- Numbered stop markers
- Polyline route paths
- Click for customer details
