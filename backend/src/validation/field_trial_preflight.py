"""Private host inventory for planned laboratory trials, not field approval."""
import argparse
import os
import platform
import shutil
import sys
from pathlib import Path
from src.archive.store import fingerprint
from src.validation.field_readiness import require,ref,read,private_path,write,result

APPROVALS=("host_authorization_ref","cost_authorization_ref","media_authorization_ref","threshold_approval_ref")

def inventory(directory):
    p=private_path(directory);require(p.is_dir(),"existing private directory required")
    require(p.stat().st_mode&0o077==0,"private directory required")
    mem=None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem=int(line.split()[1])*1024;break
    except (OSError,ValueError,IndexError):pass
    return {"os":platform.system(),"architecture":platform.machine(),"python":platform.python_version(),
            "logical_cpus":os.cpu_count(),"memory_total_bytes":mem,"disk_free_bytes":shutil.disk_usage(p).free,
            "ffmpeg_on_path":shutil.which("ffmpeg") is not None,
            "docker_on_path":shutil.which("docker") is not None}

def plan(approval,host):
    require(isinstance(approval,dict),"approval record required")
    require(approval.get("scope")=="private_lab_only" and approval.get("controller_connected") is False
            and approval.get("physical_actuation") is False,"isolated lab declaration required")
    missing=[key for key in APPROVALS if not ref(approval.get(key))]
    refs=[approval[k].strip() for k in APPROVALS if k not in missing]
    require(len(refs)==len(set(refs)),"distinct approval references required")
    require(approval.get("requested_profile")=="dedicated","dedicated profile required")
    require(approval.get("requested_duration_seconds")==86400,"full duration required")
    inventory_missing=[k for k in ("logical_cpus","memory_total_bytes","disk_free_bytes") if host.get(k) is None]
    if host.get("os")!="Linux":inventory_missing.append("Linux_host")
    for k in ("ffmpeg_on_path","docker_on_path"):
        if host.get(k) is not True:inventory_missing.append(k)
    return result("private_lab_preflight_not_execution",approval_sha256=fingerprint(approval),inventory=host,
            missing_approval_refs=missing,missing_inventory=inventory_missing,
            approvals_authenticated=False,hardware_suitable=None,soak_24h="NOT_RUN",benchmark="NOT_RUN",
            dedicated_host_verified=False,scheduler_installed=False,execution_authorized=False,
            proposed_duration_seconds=86400,required_followup=["verify_approvals_and_cost","verify_isolated_host_and_fixture","validate_B_and_record_versions","review_approved_thresholds"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--approval",required=True);p.add_argument("--private-directory",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    target=private_path(a.output);root=private_path(a.private_directory)
    require(target.parent==root,"output must be in private directory")
    write(target,plan(read(a.approval),inventory(root)))
if __name__=="__main__":main()
