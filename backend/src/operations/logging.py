import json
import logging
import sys
from datetime import datetime,timezone

class JsonFormatter(logging.Formatter):
    def format(self,record):
        payload={
            "timestamp":datetime.now(timezone.utc).isoformat(),
            "level":record.levelname,
            "logger":record.name,
            "message":record.getMessage(),
        }
        details=getattr(record,"details",None)
        if isinstance(details,dict):
            payload.update(details)
        return json.dumps(payload,separators=(",",":"),ensure_ascii=False)

def get_logger():
    logger=logging.getLogger("si.operations")
    logger.setLevel(logging.INFO)
    logger.propagate=False
    if not logger.handlers:
        handler=logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger
