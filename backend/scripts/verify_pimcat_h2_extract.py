import hashlib,json,sys
from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parents[2]
e=json.loads((root/"frontend/src/app/h2Evidence.json").read_text())
p=Path(sys.argv[1])
assert hashlib.sha256(p.read_bytes()).hexdigest()==e["zip_sha256"]
with ZipFile(p) as z:d=json.loads(z.read("study.json"))
sha=d.pop("result_sha256")
assert sha==e["report_sha256"]==hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
assert d["cases"]==e["cases"] and d["trajectories"]==e["trajectories"]
assert {r[0] for r in e["rows"]}==set(d["policies"])
for p,*values in e["rows"]:assert values==[d["summaries"]["overall"][p][k] for k in e["metrics"]]
for k,v in e["gates"].items():
    g=d["gates"]["gap_guarded"][k]
    assert v==(g["passed"] if isinstance(g,dict) else g)
for k in ("research_gate_passed","candidate_promoted","physical_actuation","c3_independent_precision","operational_decision"):
    assert d[k]==e[k]
print("H2 extract verified against original ZIP; negative gates retained")
