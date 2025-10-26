"""
Pydantic schemas package.
Import all schemas here for easy access.
"""

# Authentication schemas
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserInfo,
    OrganizationInfo,
    PasswordResetRequest,
    PasswordResetConfirm,
    ChangePasswordRequest,
)

# User schemas
from app.schemas.user import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserWithOrganizations,
    OrganizationMembership,
)

# Organization schemas
from app.schemas.organization import (
    OrganizationBase,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationWithStats,
    OrganizationUserResponse,
    InviteUserRequest,
    UpdateUserRoleRequest,
)

# Customer schemas
from app.schemas.customer import (
    CustomerBase,
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
    AssignedTechInfo,
)

# Tech schemas
from app.schemas.tech import (
    TechBase,
    TechCreate,
    TechUpdate,
    TechResponse,
    TechListResponse,
)

# Route schemas
from app.schemas.route import (
    RouteOptimizationRequest,
    RouteStopResponse,
    RouteResponse,
    RouteOptimizationResponse,
    RouteSaveRequest,
    SavedRouteResponse,
)

__all__ = [
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "UserInfo",
    "OrganizationInfo",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "ChangePasswordRequest",
    # User
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserWithOrganizations",
    "OrganizationMembership",
    # Organization
    "OrganizationBase",
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "OrganizationWithStats",
    "OrganizationUserResponse",
    "InviteUserRequest",
    "UpdateUserRoleRequest",
    # Customer
    "CustomerBase",
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    "CustomerListResponse",
    "AssignedTechInfo",
    # Tech
    "TechBase",
    "TechCreate",
    "TechUpdate",
    "TechResponse",
    "TechListResponse",
    # Route
    "RouteOptimizationRequest",
    "RouteStopResponse",
    "RouteResponse",
    "RouteOptimizationResponse",
    "RouteSaveRequest",
    "SavedRouteResponse",
]
