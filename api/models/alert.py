"""Pydantic models for alerts."""
from __future__ import annotations
from pydantic import BaseModel
class AlertAck(BaseModel):
    """Acknowledge alert body."""
    note:str|None=None
class LoginRequest(BaseModel):
    """Login credentials."""
    username:str; password:str
class TokenRefresh(BaseModel):
    """Refresh token body."""
    refresh_token:str
