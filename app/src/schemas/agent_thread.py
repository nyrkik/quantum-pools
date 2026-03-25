"""Pydantic schemas for agent thread endpoints."""

from pydantic import BaseModel
from typing import Optional


class ApproveBody(BaseModel):
    response_text: Optional[str] = None


class ReviseDraftBody(BaseModel):
    draft: str
    instruction: str


class AssignThreadBody(BaseModel):
    user_id: Optional[str] = None
    user_name: Optional[str] = None
