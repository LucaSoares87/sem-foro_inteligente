import json
from types import SimpleNamespace
import pytest
from src.validation.si13_field_packet import prepare,inspect,coverage
from src.validation.contracts import PILOT_REQUIRED


def test_draft_never_creates_valid_field_evidence(tmp_path):
    root=tmp_path/"draft"
    prepare(root)
    plan=json.loads((root/"gate-plan.json").read_text())
    assert set(plan["gates"])==PILOT_REQUIRED and plan["pilot_ready"] is False
    assert not (root/"ground-truth.json").exists()
    assert not (root/"thresholds.json").exists()
    assert not (root/"field-dossier.json").exists()
    with pytest.raises(FileNotFoundError):
        inspect(root,"missing.mp4",tmp_path)
    with pytest.raises(FileExistsError):
        prepare(root)


def test_coverage_requires_explicit_frames_and_complete_counts():
    m=SimpleNamespace(frame_count=2,dataset_id="id",classes=("car",))
    g=SimpleNamespace(lines=[SimpleNamespace(line_id="L")])
    a=SimpleNamespace(frame_sequence=1,label="car")
    c=[SimpleNamespace(line_id="L",direction=d,label=None) for d in ("negative_to_positive","positive_to_negative")]
    t=SimpleNamespace(dataset_id="id",annotations=[a],counts=c)
    coverage(t,m,g,[1,2])
    for frames in ([1],[1,1],[True,2],None):
        with pytest.raises(ValueError): coverage(t,m,g,frames)
    with pytest.raises(ValueError): coverage(SimpleNamespace(dataset_id="id",annotations=[],counts=c),m,g,[1,2])
    with pytest.raises(ValueError): coverage(SimpleNamespace(dataset_id="id",annotations=[a],counts=c[:1]),m,g,[1,2])


def test_unsubmitted_dossier_rejected(tmp_path):
    prepare(tmp_path/"draft")
    root=tmp_path/"draft"
    (root/"field-dossier.json").write_text((root/"field-dossier.draft.json").read_text())
    with pytest.raises(ValueError,match="references"):
        inspect(root,"missing.mp4",tmp_path)
