from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import json
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

MAX_SOURCES = 8
MAX_ACTIVE = 4
MAX_WIDTH = 1280
MAX_HEIGHT = 720
MAX_JPEG = 2_000_000

class SourceSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{2,80}$")
    intersection_code: str = Field(pattern=r"^[A-Z0-9_-]{2,80}$")
    kind: Literal["file", "webcam", "rtsp"]
    locator: SecretStr
    target_fps: int = Field(default=10, strict=True, ge=1, le=30)
    reconnect_attempts: int = Field(default=3, strict=True, ge=0, le=5)
    data_origin: Literal["local_authorized","external_real_replay","synthetic_demo"] = "local_authorized"
    commercial_demo_authorized: bool = False
    authorization_ref: str | None = Field(default=None,min_length=2,max_length=240)

    @model_validator(mode="after")
    def validate_locator(self):
        value = self.locator.get_secret_value()
        if not value or len(value) > 2048 or any(ord(c)<32 for c in value):
            raise ValueError("invalid source locator")
        if self.kind == "file":
            path = Path(value)
            if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in {".avi",".mp4",".mkv",".mov"}:
                raise ValueError("invalid relative video file")
        elif self.kind == "webcam":
            if value not in {str(i) for i in range(8)}:
                raise ValueError("invalid webcam index")
        else:
            parsed = urlsplit(value)
            if parsed.scheme not in {"rtsp","rtsps"} or not parsed.hostname or parsed.fragment:
                raise ValueError("invalid RTSP source")
            _ = parsed.port
        if self.commercial_demo_authorized and not self.authorization_ref:
            raise ValueError("commercial demo authorization requires reference")
        if self.data_origin == "synthetic_demo" and self.kind != "file":
            raise ValueError("synthetic demo source must be a file")
        return self

    def decoder_config(self, root: Path):
        value = self.locator.get_secret_value()
        if self.kind == "file":
            root = root.resolve()
            path = (root / value).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("video outside authorized directory")
            value = str(path)
        elif self.kind == "webcam":
            value = int(value)
        return {"kind":self.kind,"locator":value,"fps":self.target_fps}

def load_sources(raw: str):
    try:
        values = json.loads(raw)
        if not isinstance(values,list) or len(values)>MAX_SOURCES:
            raise ValueError
        sources = [SourceSpec.model_validate(item) for item in values]
        if len({s.source_id for s in sources}) != len(sources):
            raise ValueError
        return tuple(sources)
    except (ValueError, TypeError):
        raise ValueError("invalid authorized video registry") from None

@dataclass(frozen=True, slots=True)
class VideoFrame:
    source_id: str
    intersection_code: str
    sequence: int
    width: int
    height: int
    received_at: datetime
    decode_to_receive_ms: float
    jpeg: bytes
    session_id: UUID = field(default_factory=uuid4)
