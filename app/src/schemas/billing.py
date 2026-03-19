"""Pydantic schemas for billing and feature subscriptions."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FeatureTierResponse(BaseModel):
    id: str
    slug: str
    name: str
    price_cents: int
    billing_type: str
    sort_order: int

    model_config = {"from_attributes": True}


class FeatureResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str] = None
    category: str
    is_base: bool
    price_cents: int
    billing_type: str
    sort_order: int
    tiers: list[FeatureTierResponse] = []

    model_config = {"from_attributes": True}


class OrgSubscriptionResponse(BaseModel):
    id: str
    feature_id: str
    feature_slug: str
    feature_name: str
    feature_tier_id: Optional[str] = None
    tier_slug: Optional[str] = None
    tier_name: Optional[str] = None
    stripe_status: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SubscriptionSummaryResponse(BaseModel):
    subscriptions: list[OrgSubscriptionResponse]
    feature_slugs: list[str]
    total_monthly_cents: int


class SubscribeRequest(BaseModel):
    feature_slug: str
    tier_slug: Optional[str] = None


class UnsubscribeRequest(BaseModel):
    feature_slug: str
    tier_slug: Optional[str] = None
