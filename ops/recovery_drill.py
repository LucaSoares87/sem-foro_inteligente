#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

def health(url,timeout=3):
    try:
        with urllib.request.urlopen(url,timeout=timeout) as response:
            data=json.loads(response.read(2_000_000))
            return response.status,data
    except (urllib.error.URLError,ValueError,TimeoutError):
        return 0,None

def canonical(value):
    return json.dumps(value,separators=(",",":"),sort_keys=True,ensure_ascii=False).encode()

def write(path,payload):
    body=dict(payload)
    body["artifact_sha256"]=hashlib.sha256(canonical(body)).hexdigest()
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+".tmp")
    temp.write_text(json.dumps(body,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    os.chmod(temp,0o600)
    temp.replace(target)
    return body

def main():
    parser=argparse.ArgumentParser(description="Restart/recovery evidence for SI-08B.")
    parser.add_argument("--base-url",default="http://127.0.0.1:5173")
    parser.add_argument("--component",choices=["backend","postgres"],default="backend")
    parser.add_argument("--max-seconds",type=float,default=60)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    if not 5<=args.max_seconds<=300:
        raise SystemExit("invalid recovery timeout")
    url=args.base_url.rstrip("/")+"/api/v1/health"
    status,baseline=health(url)
    if status!=200 or not baseline or baseline.get("schema")!="current":
        raise SystemExit("baseline health is not ready/current")
    start=time.monotonic()
    subprocess.run(["docker","compose","restart",args.component],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=start+args.max_seconds
    final=None
    attempts=0
    while time.monotonic()<deadline:
        attempts+=1
        status,payload=health(url)
        if status==200 and payload and payload.get("status")=="ready" and payload.get("schema")=="current":
            final=payload
            break
        time.sleep(.5)
    recovered=time.monotonic()-start
    payload={
        "schema_version":1,
        "captured_at":datetime.now(timezone.utc).isoformat(),
        "component":args.component,
        "recovered":final is not None,
        "recovery_seconds":round(recovered,3),
        "attempts":attempts,
        "schema_before":baseline.get("schema"),
        "schema_after":final.get("schema") if final else None,
        "database_after":final.get("database") if final else None,
        "pilot_gate_satisfied":False,
        "physical_actuation":False,
        "note":"Recovery mechanism measurement. Target-hardware approval requires external evidence registration."
    }
    report=write(args.output,payload)
    print(json.dumps({"output":args.output,"artifact_sha256":report["artifact_sha256"],
                      "recovered":payload["recovered"],"recovery_seconds":payload["recovery_seconds"]},sort_keys=True))
    return 0 if final is not None else 6

if __name__=="__main__":
    raise SystemExit(main())
