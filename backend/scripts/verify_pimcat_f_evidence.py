"""Recheck static extract against the nine original downloaded ZIPs (offline).
Usage: python backend/scripts/verify_pimcat_f_evidence.py /path/to/zips
Expected names pimcat-f-{si11a,...,e}.zip. No network or field access.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

def digest(b):return hashlib.sha256(b).hexdigest()
def canonical(d):return digest(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def verify(root,ledger):
    for s in ledger["studies"]:
        path=root/f"pimcat-f-{s['key']}.zip"
        assert digest(path.read_bytes())==s["zip_sha256"],path
        with ZipFile(path) as z:
            name=next(n for n in z.namelist() if n.endswith(".json") and "annotation" not in n and "preflight" not in n)
            d=json.loads(z.read(name))
        assert d.pop("result_sha256")==s["report_sha256"]==canonical(d),s["id"]
        rows=d["overall"]["means"] if "overall" in d else d["fps_results"] if s["key"]=="c3" else d["summaries"]["overall"]
        assert set(rows)=={x[0] for x in s["rows"]}
        for p,*values in s["rows"]:
            assert values==[rows[p][k] for k in s["fields"]],(s["id"],p)
        assert d.get("research_gate_passed")==s["research_gate_passed"]
        assert all(d[k] is False for k in ("candidate_promoted","operationally_validated","physical_actuation"))
        if s["key"]=="c3":
            assert d["precision_state"]==ledger["c3_precision"] and d["accuracy_metrics"] is None
        else:
            count=d["overall"]["cases"] if "overall" in d else d["cases"]
            assert count==s["cases"] and count*len(rows)==s["trajectories"]
        for key,value in s["gates"].items():
            if "/" not in key:actual=d["cohorts"][key]["all_research_gates_met"]
            else:
                policy,group=key.split("/")
                actual=d["gates"][policy][group]
                if isinstance(actual,dict):actual=actual["passed"]
            assert actual==value,(s["id"],key)
        if s["key"]=="e":
            h=ledger["criticity_history"]
            row=next(x for x in d["rows"] if x["family"]==h["family"] and x["seed"]==h["seed"])
            assert h["nodes"]=={k:[v["x"],v["y"]] for k,v in row["graph"]["nodes"].items()}
            assert h["edges"]==[[k,e["from"],e["to"],e["capacity_proxy"]] for k,e in row["graph"]["edges"].items()]
            original=row["metrics"][h["policy"]]["snapshots"]
            assert h["snapshots"]==[{"tick":x["tick"],"central_available":x["central_available"],"index":[x["edges"][e[0]]["index"] for e in h["edges"]]} for x in original]
        print(s["id"],"verified")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("zip_directory",type=Path);p.add_argument("--ledger",type=Path,default=Path(__file__).resolve().parents[2]/"frontend/src/app/pimcatEvidence.json");a=p.parse_args()
    verify(a.zip_directory,json.loads(a.ledger.read_text()))
