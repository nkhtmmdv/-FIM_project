"""Pydantic models for alerts."""
from __future__ import annotations
from pydantic import BaseModel


class AlertAck(BaseModel):
    """Acknowledge alert body."""
    note: str | None = None
