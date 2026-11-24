import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from src.validation.contracts import DatasetManifest
from src.validation.io import inspect_video

BELLEVUE_TZ=ZoneInfo("America/Los_Angeles")
FILENAME_TIME=re.compile(r"__(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:\.[^.]+)$")
PROVENANCE="City-of-Bellevue/TrafficVideoDataset official public research dataset"
LICENSE_REF="Official README: research purposes; repository has no standard LICENSE file"
RESEARCH_AUTH_REF="Official Bellevue TrafficVideoDataset README public research release"

def _recorded_at(path,explicit=None):
    if explicit:
        try:
            value=datetime.fromisoformat(explicit.replace("Z","+00:00"))
        except ValueError:
            raise ValueError("invalid recorded-at timestamp") from None
        if value.tzinfo is None:
            raise ValueError("recorded-at must include timezone")
        return value
    match=FILENAME_TIME.search(Path(path).name)
    if not match:
        raise ValueError("recorded-at required when Bellevue filename has no capture timestamp")
    try:
        local=datetime.strptime(match.group(1),"%Y-%m-%d_%H-%M-%S").replace(tzinfo=BELLEVUE_TZ)
    except ValueError:
        raise ValueError("invalid Bellevue filename timestamp") from None
    return local

def prepare_bellevue_manifest(video_path,dataset_id,source_id,intersection_code,
                              recorded_at=None,inspect=inspect_video):
    info=inspect(video_path)
    if info["fps"]>30.5:
        raise ValueError("Bellevue replay exceeds supported source fps")
    return DatasetManifest(dataset_id=dataset_id,origin="external_real_replay",
        source_id=source_id,intersection_code=intersection_code,
        video_filename=Path(video_path).name,video_sha256=info["sha256"],
        provenance=PROVENANCE,license_ref=LICENSE_REF,
        authorization_ref=RESEARCH_AUTH_REF,commercial_demo_authorized=False,
        recorded_at=_recorded_at(video_path,recorded_at),
        fps=min(30.0,info["fps"]),width=info["width"],height=info["height"],
        frame_count=info["frame_count"],
        classes=("bicycle","car","motorcycle","bus","truck"))
