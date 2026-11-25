"""Offline research feedback and schedule planning, never an operational controller."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from src.archive.store import fingerprint
from src.benchmarking import pimcat_i3b_performance as p

BASE="e1296ce2ff9bee90c904e318a1139472f57f03d0"
ZONE="America/Recife"
CATALOG_SOURCE="docs/pimcat/i1-synthesis.md"
# Curated from the versioned synthesis, not independently authenticated field evidence.
STUDIES=(
    ("I1A","Xp","marginal_pass",15029745572,"5b644656ed6f8e96a6fad3e0bdaeaa1af0759a754094165b97588a7124aa969c",
     "Protected anticipation can improve pedestrian service without new deferrals.",
     "Two choices, zero new deferrals; stops 159.5 to 159.375.",
     "Marginal effect in synthetic scenarios; no operational promotion.",
     "Measure incremental benefit with independently validated demand."),
    ("I1B","ETA","failed",15028982222,"d8c443c530a4295b2814236d430e8c5d7030d2963e592cb5ec5fe042caac4fc9",
     "Calibrated arrival windows can improve coordination.",
     "Coverage 45.32 to 87.21 percent; storage 44.45 to 89.02 percent; both control gates failed.",
     "Prediction gain is not control gain.",
     "Investigate arbitration separately from prediction on a new preregistered cohort."),
    ("I1C","Xg","failed",15029547716,"4957e94109ee07d7b307327a3a1a04a5d00166e07951abb9c9b07dfb83445ebb",
     "Receiving-space weighting can reduce critical network exposure.",
     "Storage critical entries 185 to 135; delay and uninserted vehicles increased; both gates failed.",
     "Internal relief may displace queues to the boundary.",
     "Evaluate total demand including uninserted vehicles before any new control hypothesis."),
    ("I1D","Xv","null_failed",15032305730,"1bd9c4b1ac502a736be4e089798720d798ecf8205d9b02d3c19758cb5e3018cf",
     "Minor-first order may outperform proportional control at matched green budgets.",
     "128 decisions, zero inversions; identical to proportional in 32 cases.",
     "No incremental benefit demonstrated under the original guards.",
     "Study opportunity frequency without relaxing X_safe or changing historical gates."),
)

def require(ok,message):
    if not ok:raise ValueError(message)

def catalog():
    entries=[]
    for ident,domain,status,artifact,digest,hypothesis,result,limitation,question in STUDIES:
        r={"hypothesis_id":ident,"version":1,"domain":domain,"status":status,
           "hypothesis":hypothesis,"result":result,"limitation":limitation,"next_research_question":question,
           "evidence":{"source_path":CATALOG_SOURCE,"source_revision":BASE,"artifact_id":artifact,
                       "canonical_report_sha256":digest,"verification_scope":"curated_from_versioned_synthesis"},
           "candidate_promoted":False}
        r["entry_sha256"]=fingerprint(r);entries.append(r)
    return entries

def suggestion(kind,reason,evidence,question,priority,context=None):
    r={"kind":kind,"reason":reason,"priority":priority,"evidence":evidence,"research_question":question,
       "context":context,"parameter_application":False,"human_review_required":True}
    r["suggestion_sha256"]=fingerprint(r);return r

def quality_suggestions(report):
    evidence={"report_sha256":report["result_sha256"],"scope":report["scope"]}
    out=[]
    for row in report["missing_minutes"]:
        out.append(suggestion("data_quality","missing_minute",evidence,
            "Investigate missing observations; do not infer camera state.",2,dict(row)))
    for row in report["minutes"]:
        context={k:row[k] for k in ("source_id","minute","config_sha256","minute_sha256")}
        if row["unobserved_slots"]:
            out.append(suggestion("data_quality","unobserved_slots",evidence,
                "Investigate sampling coverage.",2,{**context,"count":row["unobserved_slots"]}))
        if row["unknown_slots"]:
            out.append(suggestion("data_quality","unknown_observed_slots",evidence,
                "Investigate freshness of observed frames; unknown is not physical downtime.",2,{**context,"count":row["unknown_slots"]}))
        for metric in ("fps","decode_receive_ms"):
            count=row["recent_slots"]-row[metric]["count"]
            if count:
                out.append(suggestion("data_quality","metric_missing_in_recent_slot",evidence,
                    "Investigate missing metric measurements.",2,{**context,"metric":metric,"count":count}))
    return out

def schedule_plan(reference_day):
    require(isinstance(reference_day,str),"explicit reference date required")
    d=date.fromisoformat(reference_day)
    require(d.isoformat()==reference_day,"canonical reference date required")
    zone=ZoneInfo(ZONE);rows=[]
    for offset in range(1,4):
        local=datetime.combine(d+timedelta(days=offset),time(1,0),tzinfo=zone)
        rows.append({"target_civil_date":(local.date()-timedelta(days=1)).isoformat(),
                     "planned_local":local.isoformat(),"planned_utc":local.astimezone(timezone.utc).isoformat(),
                     "state":"PLANNED_NOT_INSTALLED","execution_authorized":False})
    return {"timezone":ZONE,"reference_date":reference_day,"entries":rows,
            "scheduler_installed":False,"requirements":["authorized_private_host","verified_inputs","private_output_path","explicit_execution_authorization"],
            "overwrite":False,"missing_inputs_policy":"skip_and_record_missing_no_imputation"}

def build(reference_day,quality_input=None):
    entries=catalog()
    suggestions=[suggestion("research_blocker","independent_reference_required",
       {"source_revision":BASE,"source_path":"docs/pimcat/i2c-acquisition-status.md"},
       "Obtain independent reviewed reference and verified media before field inference.",1)]
    quality_digest=None
    if quality_input is not None:
        require(isinstance(quality_input,dict) and set(quality_input)=={"records","start","end","sources"},"invalid quality input")
        quality=p.build(quality_input["records"],quality_input["start"],quality_input["end"],quality_input["sources"])
        quality_digest=quality["result_sha256"]
        suggestions.extend(quality_suggestions(quality))
    for e in entries:
        suggestions.append(suggestion("mathematical_research",e["status"],
            {"entry_sha256":e["entry_sha256"],**e["evidence"]},e["next_research_question"],3,
            {"hypothesis_id":e["hypothesis_id"],"domain":e["domain"]}))
    out={"schema_version":1,"scope":"offline_research_feedback_not_field",
         "catalog_revision":BASE,"catalog":entries,"quality_input_report_sha256":quality_digest,
         "suggestions":suggestions,"schedule":schedule_plan(reference_day),
         "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION",
         "external_benchmark":"BLOCKED_PENDING_MEDIA_AND_REVIEW","field_speed_calibration":"NOT_RUN","soak_24h":"NOT_RUN",
         "human_acceptance":"PENDING_HUMAN","automatic_parameter_application":False,
         "physical_actuation":False,"operationally_validated":False,"candidate_promoted":False,
         "commercial_demo_authorized":False,"operational_decision":"abstain"}
    out["result_sha256"]=fingerprint(out);return out

def fixture():
    records,start,end,sources=p.fixture()
    return dict(records=records,start=start,end=end,sources=sources)

def write_exclusive(path,result):
    with Path(path).open("x",encoding="utf-8") as f:
        json.dump(result,f,sort_keys=True,indent=2,allow_nan=False)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--reference-date",required=True);parser.add_argument("--quality-input")
    parser.add_argument("--fixture",action="store_true");parser.add_argument("--output",required=True)
    args=parser.parse_args()
    require(not(args.fixture and args.quality_input),"choose at most one quality source")
    quality=None
    if args.fixture:quality=fixture()
    if args.quality_input:
        path=Path(args.quality_input);require(0<path.stat().st_size<=p.MAX_BYTES,"input size limit")
        quality=json.loads(path.read_text(encoding="utf-8"))
    write_exclusive(args.output,build(args.reference_date,quality))

if __name__=="__main__":main()
