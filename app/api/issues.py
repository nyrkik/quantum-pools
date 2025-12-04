"""
API endpoints for issue management.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.dependencies.auth import get_current_user, AuthContext
from app.models.issue import Issue
from app.models.customer import Customer
from app.models.tech import Tech
from app.models.visit import Visit
from app.schemas.issue import (
    IssueCreate,
    IssueUpdate,
    IssueResponse,
    IssueListResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.get("", response_model=IssueListResponse, summary="List issues")
async def list_issues(
    customer_id: Optional[UUID] = None,
    reported_by_tech_id: Optional[UUID] = None,
    assigned_tech_id: Optional[UUID] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of issues with optional filters.

    Filters:
    - customer_id: Filter by customer
    - reported_by_tech_id: Filter by reporting tech
    - assigned_tech_id: Filter by assigned tech
    - status: Filter by status (pending, scheduled, in_progress, resolved, closed)
    - severity: Filter by severity (low, medium, high, critical)
    """
    query = (
        select(Issue)
        .options(
            selectinload(Issue.customer),
            selectinload(Issue.reported_by),
            selectinload(Issue.assigned_tech),
            selectinload(Issue.resolved_by)
        )
        .where(Issue.organization_id == auth.organization_id)
    )

    if customer_id:
        query = query.where(Issue.customer_id == customer_id)
    if reported_by_tech_id:
        query = query.where(Issue.reported_by_tech_id == reported_by_tech_id)
    if assigned_tech_id:
        query = query.where(Issue.assigned_tech_id == assigned_tech_id)
    if status:
        query = query.where(Issue.status == status)
    if severity:
        query = query.where(Issue.severity == severity)

    query = query.order_by(Issue.reported_at.desc())

    result = await db.execute(query)
    issues = result.scalars().all()

    # Enrich with related data
    issue_responses = []
    for issue in issues:
        issue_data = IssueResponse.model_validate(issue)
        issue_data.customer_name = issue.customer.display_name if issue.customer else None
        issue_data.customer_address = issue.customer.address if issue.customer else None
        issue_data.reported_by_name = issue.reported_by.name if issue.reported_by else None
        issue_data.assigned_tech_name = issue.assigned_tech.name if issue.assigned_tech else None
        issue_data.resolved_by_name = issue.resolved_by.name if issue.resolved_by else None
        issue_responses.append(issue_data)

    return IssueListResponse(issues=issue_responses, total=len(issue_responses))


@router.get("/{issue_id}", response_model=IssueResponse, summary="Get issue by ID")
async def get_issue(
    issue_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific issue by ID."""
    result = await db.execute(
        select(Issue)
        .options(
            selectinload(Issue.customer),
            selectinload(Issue.reported_by),
            selectinload(Issue.assigned_tech),
            selectinload(Issue.resolved_by)
        )
        .where(
            Issue.id == issue_id,
            Issue.organization_id == auth.organization_id
        )
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )

    issue_data = IssueResponse.model_validate(issue)
    issue_data.customer_name = issue.customer.display_name if issue.customer else None
    issue_data.customer_address = issue.customer.address if issue.customer else None
    issue_data.reported_by_name = issue.reported_by.name if issue.reported_by else None
    issue_data.assigned_tech_name = issue.assigned_tech.name if issue.assigned_tech else None
    issue_data.resolved_by_name = issue.resolved_by.name if issue.resolved_by else None

    return issue_data


@router.post("", response_model=IssueResponse, status_code=status.HTTP_201_CREATED, summary="Create issue")
async def create_issue(
    issue_data: IssueCreate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new issue (reported by tech or office staff)."""
    # Verify customer exists and belongs to organization
    customer_result = await db.execute(
        select(Customer).where(
            Customer.id == issue_data.customer_id,
            Customer.organization_id == auth.organization_id
        )
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    # Verify visit if provided
    if issue_data.visit_id:
        visit_result = await db.execute(
            select(Visit).where(
                Visit.id == issue_data.visit_id,
                Visit.organization_id == auth.organization_id
            )
        )
        visit = visit_result.scalar_one_or_none()
        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Visit not found"
            )

    # Create issue (reported by current user's associated tech)
    # For now, use auth.user_id as reporter - in production, you'd lookup the tech associated with this user
    # Simplified: assuming user_id can be used as tech_id (adjust as needed for your auth setup)
    issue = Issue(
        organization_id=auth.organization_id,
        reported_by_tech_id=auth.user_id,  # Adjust this based on your auth setup
        **issue_data.model_dump()
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)

    # Load relationships
    await db.refresh(issue, ["customer", "reported_by"])

    issue_response = IssueResponse.model_validate(issue)
    issue_response.customer_name = issue.customer.display_name
    issue_response.customer_address = issue.customer.address
    issue_response.reported_by_name = issue.reported_by.name if issue.reported_by else None

    return issue_response


@router.put("/{issue_id}", response_model=IssueResponse, summary="Update issue")
async def update_issue(
    issue_id: UUID,
    issue_data: IssueUpdate,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an issue (assign, schedule, resolve, etc.)."""
    result = await db.execute(
        select(Issue).where(
            Issue.id == issue_id,
            Issue.organization_id == auth.organization_id
        )
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )

    # Verify assigned tech if provided
    if issue_data.assigned_tech_id:
        tech_result = await db.execute(
            select(Tech).where(
                Tech.id == issue_data.assigned_tech_id,
                Tech.organization_id == auth.organization_id
            )
        )
        tech = tech_result.scalar_one_or_none()
        if not tech:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tech not found"
            )

    # Update fields
    update_data = issue_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(issue, field, value)

    # Set resolved_at if status changed to resolved
    if issue_data.status == "resolved" and issue.status != "resolved":
        issue.resolved_at = datetime.utcnow()
        issue.resolved_by_tech_id = auth.user_id  # Adjust based on your auth setup

    await db.commit()
    await db.refresh(issue)

    # Load relationships
    await db.refresh(issue, ["customer", "reported_by", "assigned_tech", "resolved_by"])

    issue_response = IssueResponse.model_validate(issue)
    issue_response.customer_name = issue.customer.display_name
    issue_response.customer_address = issue.customer.address
    issue_response.reported_by_name = issue.reported_by.name if issue.reported_by else None
    issue_response.assigned_tech_name = issue.assigned_tech.name if issue.assigned_tech else None
    issue_response.resolved_by_name = issue.resolved_by.name if issue.resolved_by else None

    return issue_response


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete issue")
async def delete_issue(
    issue_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an issue."""
    result = await db.execute(
        select(Issue).where(
            Issue.id == issue_id,
            Issue.organization_id == auth.organization_id
        )
    )
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )

    await db.delete(issue)
    await db.commit()

    return None
