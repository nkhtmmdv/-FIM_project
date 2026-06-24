"""Baseline routes."""
from __future__ import annotations
import os
import requests
from fastapi import APIRouter, Depends, Request
from auth import current_user
from database import audit, fetch_one

router = APIRouter(prefix='/baseline', tags=['baseline'])


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
def reset(path: str, request: Request, user=Depends(current_user)):
    """Reset baseline for a single file."""
    _trigger_scanner_baseline()
    audit(user['username'], 'baseline.reset', '/' + path,
          request.client.host if request.client else None)
    return {'ok': True}


@router.get('/status')
def status(user=Depends(current_user)):
    """Return baseline status."""
    return fetch_one('SELECT COUNT(*) AS file_count, MIN(baseline_set_at) AS created_at, MAX(baseline_set_at) AS updated_at FROM baseline_hashes')
