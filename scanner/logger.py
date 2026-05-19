"""Structured JSON logging for the scanner."""
from __future__ import annotations
import hashlib, json, logging, os, time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict
LOG_DIR=os.getenv('LOG_DIR','/var/log/fim')
class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""
    def format(self, record:logging.LogRecord)->str:
        """Return a JSON encoded log record."""
        data={'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(record.created)),'level':record.levelname,'message':record.getMessage()}
        if isinstance(record.args,dict): data.update(record.args)
        return json.dumps(data,sort_keys=True)
def get_logger()->logging.Logger:
    """Create scanner logger writing to stdout and rotating file."""
    Path(LOG_DIR).mkdir(parents=True,exist_ok=True); logger=logging.getLogger('fim-scanner'); logger.setLevel(logging.INFO); logger.handlers.clear(); fmt=JsonFormatter()
    stream=logging.StreamHandler(); stream.setFormatter(fmt); logger.addHandler(stream)
    file_handler=TimedRotatingFileHandler(str(Path(LOG_DIR)/'scanner.log'),when='midnight',backupCount=30,encoding='utf-8'); file_handler.setFormatter(fmt); logger.addHandler(file_handler)
    return logger
def write_daily_checksum()->str:
    """Write SHA-256 checksum for current log file."""
    path=Path(LOG_DIR)/'scanner.log'; digest=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else hashlib.sha256(b'').hexdigest(); out=Path(LOG_DIR)/(time.strftime('scanner-%Y-%m-%d.sha256')) ; out.write_text(digest+'  scanner.log\n',encoding='utf-8'); return digest
