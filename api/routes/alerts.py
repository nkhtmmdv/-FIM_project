"""Alert routes."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query, Request
from auth import current_user
from database import audit, execute, fetch_all, fetch_one
router=APIRouter(prefix='/alerts',tags=['alerts'])
@router.get('')
def alerts(user=Depends(current_user),severity:str|None=None,event_type:str|None=None,path:str|None=None,scan_run_id:int|None=None,limit:int=Query(50,le=500),offset:int=0):
    """List alerts."""
    where=['TRUE']; params=[]
    if severity: where.append('severity=%s'); params.append(severity)
    if event_type: where.append('event_type=%s'); params.append(event_type)
    if path: where.append('file_path ILIKE %s'); params.append(f'%{path}%')
    if scan_run_id: where.append('scan_run_id=%s'); params.append(scan_run_id)
    params.extend([limit,offset]); sql='SELECT * FROM file_events WHERE '+ ' AND '.join(where)+' ORDER BY detected_at DESC LIMIT %s OFFSET %s'; return fetch_all(sql,params)
@router.get('/recent')
def recent(user=Depends(current_user)):
    """Return last twenty alerts."""
    return fetch_all('SELECT * FROM file_events ORDER BY detected_at DESC LIMIT 20')
@router.put('/{alert_id}/acknowledge')
def acknowledge(alert_id:int,request:Request,user=Depends(current_user)):
    """Acknowledge an alert."""
    execute('UPDATE file_events SET acknowledged=TRUE,acknowledged_by=%s,acknowledged_at=NOW() WHERE id=%s',(user['username'],alert_id)); audit(user['username'],'alert.ack',str(alert_id),request.client.host if request.client else None); return fetch_one('SELECT * FROM file_events WHERE id=%s',(alert_id,))
