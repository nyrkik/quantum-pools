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
    - name (required)
    - address (required)
    - service_type (required): residential or commercial
    - service_day (required): monday, tuesday, wednesday, thursday, friday, saturday, sunday
    - difficulty (optional): 1-5, defaults to 1
    - locked (optional): true/false, defaults to false
    - time_window_start (optional): HH:MM format
    - time_window_end (optional): HH:MM format
    - notes (optional)

    Parameters:
    - **geocode**: If true, geocode addresses during import (default: true, slower)
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
        csv_reader = csv.DictReader(io.StringIO(decoded))

        imported = []
        skipped = []
        errors = []

        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Required fields
                if not row.get('name') or not row.get('address'):
                    errors.append({
                        "row": row_num,
                        "error": "Missing required fields: name and address"
                    })
                    continue

                if not row.get('service_type') or row.get('service_type').lower() not in ['residential', 'commercial']:
                    errors.append({
                        "row": row_num,
                        "error": "Invalid service_type (must be residential or commercial)"
                    })
                    continue

                if not row.get('service_day'):
                    errors.append({
                        "row": row_num,
                        "error": "Missing required field: service_day"
                    })
                    continue

                # Check if customer already exists (by name and address)
                existing = await db.execute(
                    select(Customer).where(
                        Customer.name == row['name'],
                        Customer.address == row['address']
                    )
                )
                if existing.scalar_one_or_none():
                    skipped.append({
                        "row": row_num,
                        "name": row['name'],
                        "reason": "Customer already exists"
                    })
                    continue

                # Create customer
                customer_data = {
                    'name': row['name'],
                    'address': row['address'],
                    'service_type': row['service_type'].lower(),
                    'service_day': row['service_day'].lower(),
                    'difficulty': int(row.get('difficulty', 1)),
                    'locked': row.get('locked', 'false').lower() == 'true',
                    'notes': row.get('notes', ''),
                }

                # Parse time windows if provided
                if row.get('time_window_start'):
                    from datetime import time as dt_time
                    hour, minute = map(int, row['time_window_start'].split(':'))
                    customer_data['time_window_start'] = dt_time(hour, minute)

                if row.get('time_window_end'):
                    from datetime import time as dt_time
                    hour, minute = map(int, row['time_window_end'].split(':'))
                    customer_data['time_window_end'] = dt_time(hour, minute)

                customer = Customer(**customer_data)

                # Geocode if requested
                if geocode:
                    coordinates = await geocoding_service.geocode_with_rate_limit(
                        customer.address
                    )
                    if coordinates:
                        customer.latitude, customer.longitude = coordinates

                db.add(customer)
                imported.append({
                    "row": row_num,
                    "name": row['name']
                })

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "error": str(e)
                })

        # Commit all at once
        await db.commit()

        return {
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

    csv_content = """name,address,service_type,service_day,difficulty,locked,time_window_start,time_window_end,notes
John's Pool,"123 Main St, Anytown, CA 90210",residential,monday,1,false,,,Regular weekly service
ABC Corp Pool,"456 Business Blvd, Cityville, CA 90211",commercial,tuesday,3,true,10:00,14:00,Large commercial pool
Smith Residence,"789 Elm St, Townsburg, CA 90212",residential,wednesday,2,false,,,Requires gate code 1234
""".strip()

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customer_import_template.csv"}
    )
