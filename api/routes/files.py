"""File routes."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request, Query
from auth import current_user
from database import audit, execute, fetch_all, fetch_one
from models.file_record import FileAdd
router=APIRouter(prefix='/files',tags=['files'])
@router.get('')
def list_files(user=Depends(current_user), status:str|None=None, severity:str|None=None, limit:int=Query(50,le=200), offset:int=0):
    """List monitored files with latest event."""
    params=[]; where=['TRUE']
    if severity: where.append('m.severity=%s'); params.append(severity)
    clause = ' AND '.join(where)
    sql = (
        'SELECT m.*,e.event_type,e.detected_at,e.hash_after '
        'FROM monitored_files m '
        'LEFT JOIN LATERAL ('
        '  SELECT * FROM file_events e2 WHERE e2.file_path=m.file_path ORDER BY detected_at DESC LIMIT 1'
        ') e ON TRUE '
        'WHERE ' + clause + ' ORDER BY m.file_path LIMIT %s OFFSET %s'
    )
    params.extend([limit,offset]); return fetch_all(sql, params)
@router.get('/{path:path}')
def file_detail(path:str,user=Depends(current_user)):
    """Return a single file and history."""
    return {'file':fetch_one('SELECT * FROM monitored_files WHERE file_path=%s',('/'+path,)),'history':fetch_all('SELECT * FROM file_events WHERE file_path=%s ORDER BY detected_at DESC LIMIT 200',('/'+path,))}
@router.post('/add')
def add_file(body:FileAdd,request:Request,user=Depends(current_user)):
    """Add a monitored file path."""
    execute('INSERT INTO monitored_files(file_path,severity,added_by) VALUES(%s,%s,%s) ON CONFLICT(file_path) DO UPDATE SET is_active=TRUE,severity=EXCLUDED.severity',(body.file_path,body.severity,user['username'])); audit(user['username'],'file.add',body.file_path,request.client.host if request.client else None); return {'ok':True}
@router.delete('/{path:path}')
def remove_file(path:str,request:Request,user=Depends(current_user)):
    """Deactivate a monitored file path."""
    target='/'+path; execute('UPDATE monitored_files SET is_active=FALSE WHERE file_path=%s',(target,)); audit(user['username'],'file.remove',target,request.client.host if request.client else None); return {'ok':True}
