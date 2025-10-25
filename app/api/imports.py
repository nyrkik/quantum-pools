"""
CSV import API endpoints.
Provides bulk import functionality for customer data.
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import csv
import io
from typing import List

from app.database import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerResponse
from app.services.geocoding import geocoding_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post(
    "/customers/csv",
    response_model=dict,
    summary="Import customers from CSV file"
)
async def import_customers_csv(
    file: UploadFile = File(...),
    geocode: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    Import customers from a CSV file.

    Expected CSV format:
    - Client (required): Customer name
    - Address (required): Street address
    - City (required): City name
    - State (required): State abbreviation
    - Zip (required): Zip code
    - Type (required): Commercial or Residential
    - Days (required):
      - For Commercial: 2 (Mo/Th or Tu/Fr) or 3 (Mo/We/Fr)
      - For Residential: Two-letter day (Mo, Tu, We, Th, Fr, Sa, Su)
    - Difficulty (optional): 1-5, defaults to 1
    - Latitude (optional): Will geocode if not provided
    - Longitude (optional): Will geocode if not provided

    Parameters:
    - **geocode**: If true, geocode addresses without coordinates (default: true)
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )

    try:
        # Read CSV file
        contents = await file.read()
        decoded = contents.decode('utf-8')

        # Detect delimiter (tab or comma)
        sample = decoded[:1000]
        delimiter = '\t' if '\t' in sample and sample.count('\t') > sample.count(',') else ','

        csv_reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)

        logger.info(f"Starting CSV import from file: {file.filename} (delimiter: {repr(delimiter)})")

        imported = []
        skipped = []
        errors = []
        row_num = 1
        commercial_2x_counter = 0  # Track alternating schedules for 2x/week customers

        # Day mapping
        day_map = {
            'Mo': 'monday',
            'Tu': 'tuesday',
            'We': 'wednesday',
            'Th': 'thursday',
            'Fr': 'friday',
            'Sa': 'saturday',
            'Su': 'sunday'
        }

        # Commercial schedule mapping
        commercial_schedules = {
            '2': [['monday', 'thursday'], ['tuesday', 'friday']],
            '3': [['monday', 'wednesday', 'friday']]
        }

        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
            try:
                logger.info(f"Processing row {row_num}: {dict(row)}")

                # Required fields
                client = row.get('Client', '').strip()
                address = row.get('Address', '').strip()
                city = row.get('City', '').strip()
                state = row.get('State', '').strip()
                zip_code = row.get('Zip', '').strip()
                service_type = row.get('Type', '').strip().lower()
                days = row.get('Days', '').strip()

                if not client or not address or not city or not state or not zip_code:
                    errors.append({
                        "row": row_num,
                        "error": "Missing required fields: Client, Address, City, State, Zip"
                    })
                    continue

                if service_type not in ['commercial', 'residential']:
                    errors.append({
                        "row": row_num,
                        "error": f"Invalid Type: must be 'Commercial' or 'Residential', got '{row.get('Type')}'"
                    })
                    continue

                if not days:
                    errors.append({
                        "row": row_num,
                        "error": "Missing required field: Days"
                    })
                    continue

                # Build full address
                full_address = f"{address}, {city}, {state} {zip_code}"

                # Parse difficulty
                difficulty_str = row.get('Difficulty', '1').strip()
                difficulty = int(difficulty_str) if difficulty_str else 1
                if difficulty < 1 or difficulty > 5:
                    difficulty = 1

                # Parse coordinates if provided
                provided_lat = row.get('Latitude', '').strip()
                provided_lon = row.get('Longitude', '').strip()
                latitude = float(provided_lat) if provided_lat else None
                longitude = float(provided_lon) if provided_lon else None

                # Determine service schedule
                service_days_per_week = 1
                service_schedule = None
                primary_day = None

                if service_type == 'commercial':
                    if days == '2':
                        service_days_per_week = 2
                        # Alternate between Mo/Th and Tu/Fr for load balancing
                        if commercial_2x_counter % 2 == 0:
                            service_schedule = 'Mo/Th'
                            primary_day = 'monday'
                        else:
                            service_schedule = 'Tu/Fr'
                            primary_day = 'tuesday'
                        commercial_2x_counter += 1
                    elif days == '3':
                        service_days_per_week = 3
                        service_schedule = 'Mo/We/Fr'
                        primary_day = 'monday'
                    else:
                        errors.append({
                            "row": row_num,
                            "error": f"Invalid Days for commercial: must be 2 or 3, got '{days}'"
                        })
                        continue
                else:  # residential
                    if days in day_map:
                        service_days_per_week = 1
                        service_schedule = None
                        primary_day = day_map[days]
                    else:
                        errors.append({
                            "row": row_num,
                            "error": f"Invalid Days for residential: must be Mo, Tu, We, Th, Fr, Sa, or Su, got '{days}'"
                        })
                        continue

                # Check if customer already exists
                existing = await db.execute(
                    select(Customer).where(
                        Customer.name == client,
                        Customer.address == full_address
                    )
                )
                if existing.scalar_one_or_none():
                    skipped.append({
                        "row": row_num,
                        "name": client,
                        "reason": "Customer already exists"
                    })
                    continue

                # Create single customer record with schedule info
                customer = Customer(
                    name=client,
                    address=full_address,
                    service_type=service_type,
                    service_day=primary_day,
                    service_days_per_week=service_days_per_week,
                    service_schedule=service_schedule,
                    difficulty=difficulty,
                    latitude=latitude,
                    longitude=longitude
                )

                # Geocode if coordinates not provided and geocode enabled
                if geocode and (latitude is None or longitude is None):
                    coordinates = await geocoding_service.geocode_with_rate_limit(full_address)
                    if coordinates:
                        customer.latitude, customer.longitude = coordinates

                db.add(customer)
                imported.append({
                    "row": row_num,
                    "name": client,
                    "service_schedule": service_schedule or primary_day
                })

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "error": str(e)
                })

        # Commit all at once
        await db.commit()

        result = {
            "status": "completed",
            "total_rows": row_num - 1,  # Exclude header
            "imported": len(imported),
            "skipped": len(skipped),
            "errors": len(errors),
            "imported_customers": imported,
            "skipped_customers": skipped,
            "error_details": errors,
            "geocoded": geocode
        }

        logger.info(f"Import completed: {result['imported']} imported, {result['skipped']} skipped, {result['errors']} errors")
        if errors:
            logger.warning(f"Import errors: {errors}")

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV file: {str(e)}"
        )


@router.get(
    "/customers/template",
    summary="Download CSV template for customer import"
)
async def download_csv_template():
    """
    Download a CSV template file for importing customers.

    Returns a sample CSV with proper headers and example data.
    """
    from fastapi.responses import StreamingResponse

    csv_content = """Client,Address,City,State,Zip,Type,Days,Difficulty,Latitude,Longitude
John's Pool,123 Main St,Anytown,CA,90210,Residential,Mo,1,,
Smith Residence,456 Elm St,Cityville,CA,90211,Residential,We,2,,
ABC Corp Pool,789 Business Blvd,Townsburg,CA,90212,Commercial,2,3,,
XYZ Commercial,321 Industry Dr,Metropolis,CA,90213,Commercial,3,4,,
""".strip()

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customer_import_template.csv"}
    )
