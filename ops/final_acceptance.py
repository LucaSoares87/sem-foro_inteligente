"""Isolated synthetic acceptance environment. No field evidence or camera configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "si-acceptance-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
STATE = Path.home() / ".local" / "state" / PROJECT
BASE = "http://127.0.0.1:5173"
GATES = {"authorized_model", "physical_camera", "calibration", "field_ground_truth",
         "hardware_benchmark", "recovery_drill", "human_acceptance"}
ROUTES = ("executivo", "videowall", "operacional", "laboratorio", "apresentacao", "homologacao")
PRESETS = ("balanced", "asymmetric", "surge", "overload", "empty")
SETTINGS = {
    "APP_ENV": "development", "AUTH_MODE": "disabled", "POSTGRES_DB": "traffic",
    "POSTGRES_USER": "traffic", "WEB_PORT": "5173", "VIDEO_SOURCES_JSON": "[]",
    "VISION_MODEL_JSON": "", "TRAFFIC_GEOMETRY_JSON": "[]",
    "INTERSECTION_REGISTRY_JSON": "[]", "VALIDATION_EVIDENCE_JSON": "[]",
    "AUDIT_ENABLED": "true", "ALLOWED_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
    "BACKEND_CPU_LIMIT": "2.0", "BACKEND_MEMORY_LIMIT": "2g",
    "POSTGRES_CPU_LIMIT": "2.0", "POSTGRES_MEMORY_LIMIT": "1g",
    "FRONTEND_CPU_LIMIT": "1.0", "FRONTEND_MEMORY_LIMIT": "256m",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def password(create=False):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not STATE.is_symlink() and STATE.stat().st_uid == os.getuid()
            and STATE.stat().st_mode & 0o077 == 0, "private state directory required")
    path = STATE / "postgres-password"
    if create and not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    require(path.is_file() and not path.is_symlink() and path.stat().st_uid == os.getuid()
            and path.stat().st_mode & 0o077 == 0, "run start first; private password required")
    result = path.read_text()
    require(bool(re.fullmatch(r"[0-9a-f]{64}", result)), "invalid private password")
    return result


def isolated_env(secret):
    # Do not inherit Compose variables, field credentials, source registries or proxy settings.
    e = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "USER")
         if k in os.environ}
    return {**e, **SETTINGS, "POSTGRES_PASSWORD": secret}


def compose(args, env, capture=False):
    cmd = ["docker", "--context", "default", "compose", "--project-name", PROJECT,
           "--project-directory", str(ROOT), "--env-file", "/dev/null",
           "-f", str(ROOT / "docker-compose.yml"), *args]
    # Config contains a password; never print its stdout or stderr.
    p = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=capture, timeout=600)
    if p.returncode:
        raise RuntimeError("Compose failed: " + args[0])
    return p.stdout if capture else None


def validate_config(config):
    require(config.get("name") == PROJECT, "wrong project")
    services = config["services"]
    require(set(services) == {"postgres", "migrate", "backend", "frontend"}, "unexpected service")
    for key in ("APP_ENV", "AUTH_MODE", "VIDEO_SOURCES_JSON", "VISION_MODEL_JSON",
                "TRAFFIC_GEOMETRY_JSON", "INTERSECTION_REGISTRY_JSON", "VALIDATION_EVIDENCE_JSON"):
        require(services["backend"]["environment"].get(key) == SETTINGS[key], "unexpected " + key)
    require(not services["backend"].get("volumes") and not services["backend"].get("devices"),
            "unexpected camera/model mount")
    require(all(not services[x].get("ports") for x in ("postgres", "migrate", "backend")),
            "unexpected published backend port")
    ports = services["frontend"].get("ports", [])
    require(len(ports) == 1 and ports[0].get("host_ip") == "127.0.0.1"
            and str(ports[0].get("published")) == "5173" and ports[0].get("target") == 8080,
            "frontend must bind only to loopback")
    require(services["postgres"]["environment"]["POSTGRES_DB"] == "traffic",
            "unexpected database")
    require(not any(v.get("external") for v in config.get("volumes", {}).values()),
            "external volumes forbidden")


def preflight(env):
    # Explicit default local Docker context; reject a remote daemon.
    p = subprocess.run(["docker", "context", "inspect", "default"], env=env, text=True,
                       capture_output=True, check=True, timeout=10)
    host = json.loads(p.stdout)[0]["Endpoints"]["docker"]["Host"]
    require(host.startswith("unix://"), "local Linux Docker daemon required")
    validate_config(json.loads(compose(["config", "--format", "json"], env, capture=True)))


def get(path, expected=200, as_json=True):
    req = urllib.request.Request(BASE + path, headers={"Cache-Control": "no-store"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as response:
            code, raw = response.status, response.read(2_000_000)
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read(2_000_000)
    require(code == expected, "unexpected HTTP status for " + path)
    return json.loads(raw) if as_json else raw


def verify_runtime():
    h = get("/api/v1/health")
    require(h["status"] == "ready" and h["database"] == "online" and h["schema"] == "current",
            "application not ready")
    require(h["video"]["sources"] == [], "unexpected video source")
    v = get("/api/v1/validation/status")
    require(v["state"] == "available" and v["framework_ready"] is True
            and v["pilot_ready"] is False and v["physical_actuation"] is False
            and v["operational_decision"] == "abstain" and set(v["missing_evidence"]) == GATES,
            "field boundary violation")
    require(v["runtime_observation"]["physical_sources_configured"] == 0
            and v["runtime_observation"]["authorized_candidate_model_loaded"] is False,
            "unexpected field runtime")
    return sorted(v["missing_evidence"])


def run_checks():
    missing = verify_runtime()
    routes = []
    for route in ROUTES:
        raw = get("/" + route, as_json=False)
        require(b'id="root"' in raw, "SPA route unavailable: " + route)
        routes.append(route)
    demos = {}
    for preset in PRESETS:
        path = "/api/v1/decision/demo?preset=" + preset
        a, b = get(path), get(path)
        require(a == b and a["origin"] == "synthetic" and a["execution_mode"] == "simulation"
                and a["physical_actuation"] is False and a["operationally_validated"] is False,
                "non-reproducible or non-synthetic demo")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", a["result_sha256"])), "invalid digest")
        for key in ("fixed", "adaptive"):
            p = a[key]
            require(p["initial_queue"] + p["arrivals"] == p["served"] + p["final_queue"],
                    "vehicle conservation")
        demos[preset] = {"result_sha256": a["result_sha256"], "preference": a["preferred_in_simulation"]}
    get("/api/v1/decision/demo?preset=invalid", expected=422)
    require(len({d["result_sha256"] for d in demos.values()}) == len(PRESETS), "preset digest collision")
    return {"scope": "synthetic_human_acceptance_preparation", "routes_http": routes,
            "presets": demos, "missing_field_gates": missing, "physical_actuation": False,
            "pilot_ready": False, "candidate_promoted": False, "human_acceptance": "PENDING_HUMAN"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("start", "status", "test", "stop"))
    p.add_argument("--output", type=Path, help="new JSON report for test only")
    a = p.parse_args()
    if a.output and (a.command != "test" or a.output.exists()):
        p.error("output must be a new file for test")
    if a.command == "stop" and not STATE.exists():
        print("No acceptance environment initialized.")
        return
    env = isolated_env(password(a.command == "start"))
    preflight(env)
    if a.command == "start":
        compose(["up", "--build", "--wait", "--wait-timeout", "180"], env)
        verify_runtime()
        print("Demonstração exclusivamente sintética: " + BASE + "/executivo")
        print("Codespaces: confira visibilidade Private da porta 5173 antes de abrir.")
    elif a.command == "stop":
        compose(["stop"], env)
    elif a.command == "status":
        compose(["ps"], env)
        print(json.dumps({"missing_field_gates": verify_runtime(), "human_acceptance": "PENDING_HUMAN"}))
    else:
        report = run_checks()
        if a.output:
            with a.output.open("x", encoding="utf-8") as f:
                json.dump(report, f, indent=2, sort_keys=True)
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as e:
        print("Acceptance command failed: " + type(e).__name__ + ": " + str(e), file=sys.stderr)
        sys.exit(1)
