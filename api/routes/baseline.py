"""Baseline routes."""
from __future__ import annotations
import os, requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from auth import current_user, verify_password
from database import audit, execute, fetch_all, fetch_one
router=APIRouter(prefix='/baseline',tags=['baseline'])
class Confirm(BaseModel):
    """Password confirmation body."""
    password:str
def _trigger_scanner_baseline():
    try:
        requests.post(
            'http://scanner:9000/api/baseline/reset',
            headers={'X-Confirmation-Token': os.getenv('BASELINE_CONFIRMATION_TOKEN', '')},
            timeout=5
        )
    except requests.RequestException:
        pass

@router.post('/create')
def create(request: Request, user=Depends(current_user)):
    """Trigger baseline creation."""
    _trigger_scanner_baseline()
    audit(user['username'], 'baseline.create', 'all',
          request.client.host if request.client else None)
    return {'ok': True}

@router.post('/reset/{path:path}')
def reset(path: str, body: Confirm, request: Request, user=Depends(current_user)):
    """Reset baseline after password reconfirmation."""
    row = fetch_one('SELECT password_hash FROM users WHERE username=%s', (user['username'],))
    if not row or not verify_password(body.password, row['password_hash']):
        raise HTTPException(status_code=403, detail='password confirmation failed')
    _trigger_scanner_baseline()
    audit(user['username'], 'baseline.reset', '/' + path,
          request.client.host if request.client else None)
    return {'ok': True}
@router.get('/status')
def status(user=Depends(current_user)):
    """Return baseline status."""
    return fetch_one('SELECT COUNT(*) AS file_count, MIN(baseline_set_at) AS created_at, MAX(baseline_set_at) AS updated_at FROM baseline_hashes')
