"""FIM scanning and comparison engine."""
from __future__ import annotations
import time
import logging
from typing import Dict, List, Tuple
import yaml
import alerter
import db
from hasher import expand_paths, snapshot
from logger import get_logger
CONFIG_PATH='config.yaml'; LOGGER=get_logger()
def load_config()->Dict[str,object]:
    """Load YAML scanner configuration."""
    with open(CONFIG_PATH,'r',encoding='utf-8') as handle: return yaml.safe_load(handle)
def severity_for(path:str, mapping:Dict[str,str])->str:
    """Determine severity from configured prefixes."""
    from pathlib import Path
    best='INFO'
    for prefix, sev in mapping.items():
        if path.startswith(prefix): best=sev
    parts = set(Path(path).parts)
    return 'CRITICAL' if parts & {'bin', 'sbin'} else best
def compare(scan_id:int, snaps:Dict[str,Dict[str,object]], base:Dict[str,Dict[str,object]], sev:Dict[str,str], cfg:Dict[str,object])->Tuple[List[Dict[str,object]],Dict[str,int]]:
    """Compare snapshots to baseline and persist events.

    Returns only **newly written** events (no stale duplicates).
    This prevents repeat Telegram alerts for already-known unacked changes.
    """
    events=[]; stats={'scanned':len(snaps),'clean':0,'modified':0,'deleted':0,'added':0,'permissions_changed':0,'owner_changed':0}
    for path,s in snaps.items():
        b=base.get(path); kind='UNCHANGED'
        if not b:
            if s['sha256_hash'] in ('DELETED','UNREADABLE'): continue
            kind='ADDED'
        elif s['sha256_hash']=='DELETED':
            if (b or {}).get('sha256_hash')=='DELETED': continue
            kind='DELETED'
        elif s['sha256_hash']!=b['sha256_hash']:
            # Content changed — absorb any simultaneous owner change into one event
            if b['owner_uid'] is not None and b['owner_gid'] is not None and (s['owner_uid']!=b['owner_uid'] or s['owner_gid']!=b['owner_gid']):
                kind='MODIFIED_WITH_OWNER_CHANGE'
            else:
                kind='MODIFIED'
        elif cfg.get('alert_on_permission_change',True) and s['permissions']!=b['permissions']:
            kind='PERMISSIONS_CHANGED'
        elif cfg.get('alert_on_owner_change',True) and (
            b['owner_uid'] is not None and b['owner_gid'] is not None and
            (s['owner_uid']!=b['owner_uid'] or s['owner_gid']!=b['owner_gid'])
        ):
            kind='OWNER_CHANGED'

        if kind=='UNCHANGED': stats['clean']+=1; continue
        if kind=='ADDED' and not cfg.get('alert_on_new_files',True): continue
        if kind=='DELETED' and not cfg.get('alert_on_deleted_files',True): continue
        if kind in ('MODIFIED','MODIFIED_WITH_OWNER_CHANGE'): stats['modified']+=1
        elif kind=='DELETED': stats['deleted']+=1
        elif kind=='ADDED': stats['added']+=1
        elif kind=='PERMISSIONS_CHANGED': stats['permissions_changed']+=1
        elif kind=='OWNER_CHANGED': stats['owner_changed']+=1

        ev = {
            'file_path': path,
            'event_type': kind,
            'severity': severity_for(path, sev),
            'hash_before': None if not b else b['sha256_hash'],
            'hash_after': s['sha256_hash'],
            'size_before': None if not b else b['file_size'],
            'size_after': s['file_size'],
            'permissions_before': None if not b else b['permissions'],
            'permissions_after': s['permissions'],
            'owner_before': None if not b else b['owner_name'],
            'owner_after': s['owner_name'],
        }
        # Only add to events (and alert) if this is a genuinely NEW finding
        if not db.has_unacked_duplicate(path, s['sha256_hash'], scan_id):
            db.auto_ack_superseded(path, scan_id)  # silence stale old alerts for this file
            db.write_event(scan_id, ev)
            LOGGER.warning('file_change', {
                'scan_id': scan_id, 'file_path': path,
                'event_type': kind, 'hash_before': ev['hash_before'], 'hash_after': ev['hash_after'],
            })
            events.append(ev)

    for path, b in base.items():
        if path not in snaps and cfg.get('alert_on_deleted_files', True):
            ev = {
                'file_path': path, 'event_type': 'DELETED',
                'severity': severity_for(path, sev),
                'hash_before': b['sha256_hash'], 'hash_after': 'DELETED',
                'size_before': b['file_size'], 'size_after': None,
                'permissions_before': b['permissions'], 'permissions_after': None,
                'owner_before': b['owner_name'], 'owner_after': None,
            }
            if not db.has_unacked_duplicate(path, 'DELETED', scan_id):
                db.auto_ack_superseded(path, scan_id)
                db.write_event(scan_id, ev)
                events.append(ev)
            stats['deleted']+=1

    return events, stats


def run_scan(triggered_by: str = 'scheduler', reset_baseline: bool = False) -> int:
    """Execute one scan and optionally replace baseline."""
    started = time.time()
    cfg = load_config()
    paths = db.monitored_paths() or cfg['monitored_files']
    expanded = expand_paths(paths)
    logging.info('scan_start triggered_by=%s monitored_paths=%s expanded_count=%s', triggered_by, paths, len(expanded))
    scan_id = db.start_scan(triggered_by)

    try:
        snaps = {p: snapshot(p).to_dict() for p in expanded}
        first = not db.baseline_exists()
        if first or reset_baseline:
            db.replace_baseline(scan_id, snaps.values())
            stats = {
                'duration_ms': int((time.time() - started) * 1000),
                'scanned': len(snaps),
                'clean': len(snaps),
                'modified': 0,
                'deleted': 0,
                'added': 0,
            }
            db.finish_scan(scan_id, stats, 'BASELINE_CREATED')
            return scan_id

        events, stats = compare(scan_id, snaps, db.load_baseline(), db.severities(), cfg)
        stats['duration_ms'] = int((time.time() - started) * 1000)
        db.finish_scan(scan_id, stats, 'COMPLETE')
        # events now contains only genuinely new findings (not already-known unacked duplicates)
        alerts = list(events)

        alerter.dispatch(alerts)

        # Baseline advances only when user acknowledges — no auto-update here.
        return scan_id
    except Exception as exc:
        db.finish_scan(
            scan_id,
            {'duration_ms': int((time.time() - started) * 1000)},
            'FAILED',
        )
        LOGGER.error(str(exc), {'scan_id': scan_id, 'event_type': 'SCAN_FAILED'})
        raise
