"""Pydantic models for monitored file records."""
from __future__ import annotations
from pydantic import BaseModel, Field


class FileAdd(BaseModel):
    """Request to add a monitored path."""
    file_path: str = Field(min_length=1, max_length=4096)
    severity: str = Field(default='WARNING', pattern='^(CRITICAL|WARNING|INFO)$')


class FileRecord(BaseModel):
    """Monitored file response model."""
    id: int
    file_path: str
    is_active: bool
    severity: str
