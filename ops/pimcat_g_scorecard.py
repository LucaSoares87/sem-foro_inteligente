"""Generate acceptance evidence only from actual JUnit execution, never sign field/human approval."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

def build(junit,revision):
    matrix=json.loads((ROOT/"docs/pimcat/g-scenarios.json").read_text())
    ledger=json.loads((ROOT/"frontend/src/app/pimcatEvidence.json").read_text())
    tree=ET.parse(junit)
    tests={}
    for c in tree.iter("testcase"):
        name=c.get("name","")
        if name.startswith("test_scenario_"):
            assert name not in tests
            tests[name]=not any(c.find(tag) is not None for tag in ("failure","error","skipped"))
    expected={"test_"+s["test"] for s in matrix["scenarios"]}
    assert set(tests)==expected and all(tests.values())
    assert len(tests)==27
    assert all(s["research_gate_passed"] is not True and not s["candidate_promoted"] for s in ledger["studies"])
    assert ledger["c3_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"
    matrix["scenarios"]=[{**s,"regression":"passed"} for s in matrix["scenarios"]]
    matrix["revision"]=revision
    matrix["junit_sha256"]=hashlib.sha256(Path(junit).read_bytes()).hexdigest()
    matrix["dispositions"]={k:sum(s["disposition"]==k for s in matrix["scenarios"]) for k in ("PASS_SCOPED","PARTIAL","BLOCKED")}
    matrix["study_reports"]=[{k:s[k] for k in ("id","run","artifact","report_sha256","research_gate_passed","origin")} for s in ledger["studies"]]
    matrix["research_regression_passed"]=True
    matrix["human_acceptance"]="PENDING_HUMAN"
    matrix["pilot_decision"]="blocked_by_field_evidence"
    matrix["operational_decision"]="abstain"
    return matrix
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--junit",required=True,type=Path);p.add_argument("--revision",required=True);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    with a.output.open("x") as f:json.dump(build(a.junit,a.revision),f,ensure_ascii=False,indent=2)
