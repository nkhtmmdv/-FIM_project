"""Secure file metadata collection and hashing."""
from __future__ import annotations
import hashlib, os, pwd, stat
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional
CHUNK_SIZE=1024*1024
@dataclass(frozen=True)
class FileSnapshot:
    """Represents one filesystem snapshot."""
    file_path:str; sha256_hash:str; file_size:Optional[int]; mtime:Optional[float]; owner_uid:Optional[int]; owner_gid:Optional[int]; owner_name:str; permissions:str; inode:Optional[int]; status:str; is_symlink:bool; link_target:Optional[str]
    def to_dict(self)->Dict[str, object]:
        """Return a serialisable dictionary."""
        return asdict(self)
def _owner(uid:int)->str:
    """Resolve an owner name from uid."""
    try: return pwd.getpwuid(uid).pw_name
    except KeyError: return str(uid)
def _hash(path:Path)->str:
    """Compute a SHA-256 hash for a regular file."""
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b''):
            digest.update(chunk)
    return digest.hexdigest()
def snapshot(path:str)->FileSnapshot:
    """Collect metadata and hash for path without crashing on errors."""
    p=Path(path)
    try:
        st=os.lstat(p)
    except FileNotFoundError:
        return FileSnapshot(path,'DELETED',None,None,None,None,'','',None,'DELETED',False,None)
    except PermissionError:
        return FileSnapshot(path,'UNREADABLE',None,None,None,None,'','',None,'UNREADABLE',False,None)
    is_link=stat.S_ISLNK(st.st_mode); perms=oct(stat.S_IMODE(st.st_mode))[2:].zfill(3); target=None
    try:
        target=os.readlink(p) if is_link else None
        digest=hashlib.sha256((target or '').encode()).hexdigest() if is_link else _hash(p)
        status='SYMLINK' if is_link else 'OK'
    except PermissionError:
        digest='UNREADABLE'; status='UNREADABLE'
    except OSError:
        digest='UNREADABLE'; status='UNREADABLE'
    return FileSnapshot(path,digest,st.st_size,st.st_mtime,st.st_uid,st.st_gid,_owner(st.st_uid),perms,st.st_ino,status,is_link,target)
def expand_paths(paths:Iterable[str])->List[str]:
    """Expand monitored files and directories recursively."""
    found=[]
    for item in paths:
        p=Path(item)
        if p.is_dir():
            for root, dirs, names in os.walk(p, followlinks=False):
                dirs.sort(); names.sort()
                for name in names: found.append(str(Path(root)/name))
        else:
            found.append(str(p))
    return sorted(set(found))
