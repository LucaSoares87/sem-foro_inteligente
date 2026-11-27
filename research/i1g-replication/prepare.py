"""Prepare the original executor and a receipt for a reviewed manual dispatch."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

here = Path(__file__).resolve().parent
repo = here.parents[1]
root = Path(sys.argv[1])
root.mkdir()
with ZipFile(here.parent / "i1g-regression/fixtures.zip") as archive:
    archive.extractall(root)
with ZipFile(here / "proofs.zip") as archive:
    archive.extractall(root / "proofs")
proofs = root / "proofs"
evidence = json.loads((proofs / "evidence.json").read_bytes())
shutil.copyfile(proofs / "baseline/real-parity-report.json", root / "real-parity-report.json")
for row in json.loads((root / "source-manifest.json").read_bytes()):
    path = Path(row["path"])
    original = proofs / "baseline" / path
    src = original if original.is_file() else repo / path
    assert hashlib.sha256(src.read_bytes()).hexdigest() == row["sha256"], path
    dest = root / "repo" / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
assert os.environ["REVIEWED_SHA"] == os.environ["GITHUB_SHA"]
approval = {k: evidence[k] for k in ("additional_target_proofs", "tests_sha256", "source_manifest_sha256")}
approval.update(approved=True, budget_job_min=10, purpose="PIMCAT-I1G-REPLICATION-ONLY",
                plan_sha256=evidence["plan_sha256_canonical"], base_commit=evidence["baseline_commit"],
                release_commit=os.environ["REVIEWED_SHA"], release_review_complete=True)
(root / "approval.json").write_text(json.dumps(approval, indent=2))
