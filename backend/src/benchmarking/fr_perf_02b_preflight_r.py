"""Bounded synthetic technical preflight; no screening or municipal input."""
import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

from src.benchmarking.fr_perf_02b import (
    Detector, MODEL, SCREENING_RELEASED, SLOTS, digest, distribution,
    matched_differences, measured_block, paired_overhead, runtime_info, save,
)
from src.benchmarking.fr_perf_01a import synthetic_frames
from src.benchmarking.si10_cpu_profile import cpu_budget
from src.video.manager import child_environment
from src.vision.contracts import Detection, ModelSpec
from src.vision.service import InferenceWorker
from src.vision.worker import LENGTH

def plain_child(backend, threads):
    """Original worker framing, serialization and clocks; no added telemetry."""
    from src.vision import worker, yolo
    original = yolo.YoloDetector
    # Detector uses the original OpenCV constructor. Avoid recursion while constructing.
    class PlainDetector:
        def __init__(self, path, spec):
            yolo.YoloDetector = original
            try:
                self.detector = Detector(path, spec, backend, threads)
            finally:
                yolo.YoloDetector = PlainDetector
        def infer(self, image):
            return self.detector.infer(image, profile=False)[0]
    if threads not in (2, 4) or threads > cpu_budget()["thread_budget"]:
        raise ValueError("invalid CPU budget")
    yolo.YoloDetector = PlainDetector
    try:
        return worker.main()
    finally:
        yolo.YoloDetector = original

class PlainWorker(InferenceWorker):
    def __init__(self, spec, root, backend, threads):
        super().__init__(spec, root)
        self.backend, self.threads = backend, threads
    async def open(self):
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", __name__ if __name__ != "__main__" else "src.benchmarking.fr_perf_02b_preflight_r",
            "--plain-worker", self.backend, str(self.threads),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=child_environment(), limit=65536)
        async with asyncio.timeout(30):
            self.process.stdin.write(json.dumps({"spec": self.spec.model_dump(mode="json"), "root": str(self.root)}).encode()+b"\n")
            await self.process.stdin.drain()
            if (await self._reply()).get("state") != "ready":
                raise ValueError("plain worker load failed")

async def plain_block(spec, root, backend, threads, frames):
    worker = PlainWorker(spec, root, backend, threads)
    times, outputs = [], []
    try:
        await worker.open()
        for jpeg in frames[:3]:
            await worker.infer(jpeg)
        for jpeg in frames:
            start = time.monotonic_ns()
            raw = await worker.infer(jpeg)
            times.append((time.monotonic_ns()-start)/1e6)
            outputs.append(tuple(Detection.model_validate(x) for x in raw["detections"]))
        return times, outputs
    finally:
        await worker.close()

def negative_ipc(spec, root, backend, threads, mode, payload):
    module = "src.benchmarking.fr_perf_02b_preflight_r" if mode == "plain" else "src.benchmarking.fr_perf_02b"
    flag = "--plain-worker" if mode == "plain" else "--worker"
    cmd = [sys.executable, "-m", module, flag, backend, str(threads)]
    if mode == "profile":
        cmd.append("profile")
    init = json.dumps({"spec": spec.model_dump(mode="json"), "root": str(root)}).encode()+b"\n"
    result = subprocess.run(cmd, input=init+payload, capture_output=True, timeout=40, env=child_environment())
    replies = [json.loads(x) for x in result.stdout.splitlines()]
    ok = bool(replies) and replies[0].get("state") == "ready" and result.returncode != 0 and not any(x.get("state") == "ok" for x in replies)
    return {"passed": ok, "exit_code": result.returncode, "states": [x.get("state") for x in replies]}

async def run(spec, root, output):
    if SCREENING_RELEASED:
        raise ValueError("unexpected screening release")
    if digest(spec.resolve(root).read_bytes()) != MODEL:
        raise ValueError("wrong model bytes")
    hw = cpu_budget()
    threads_list = [n for n in (2,4) if n <= hw["thread_budget"]]
    if not threads_list:
        raise ValueError("insufficient CPU budget")
    source = synthetic_frames()
    frames = [source[k] for k in SLOTS[:4]]
    del source
    report = dict(scope="synthetic_technical_preflight_not_screening", model_sha256=MODEL,
        hardware=hw, environment=runtime_info(), input_hashes=[digest(x) for x in frames],
        arms=[], negative_ipc=[], complete=False, screening_released=False, candidate_promoted=False,
        physical_actuation=False, operational_decision="abstain", human_acceptance="PENDING_HUMAN",
        phase_b="DEFERRED", soak_24h="NOT_RUN")
    try:
        async with asyncio.timeout(225):
            references = {}
            for n in threads_list:
                for backend in ("ocv","ort"):
                    plain, profiled, traces = [], [], []
                    arm = dict(backend=backend, threads=n, blocks=[])
                    report["arms"].append(arm)
                    for profile in (False, True, True, False):
                        if profile:
                            rows, ds, cpu, parent_cpu = await measured_block(spec, root, backend, n, frames, True)
                            times = [x["ipc_roundtrip_ms"] for x in rows]
                            arm["blocks"].append(dict(mode="profile", rows=rows, worker_cpu_per_frame=cpu, parent_cpu_per_frame=parent_cpu))
                            profiled.extend(times)
                        else:
                            times, ds = await plain_block(spec, root, backend, n, frames)
                            plain.extend(times)
                            arm["blocks"].append(dict(mode="plain", roundtrips_ms=times))
                        traces.append(ds)
                    arm["overhead"] = paired_overhead(plain, profiled)
                    arm["plain_distribution"] = distribution(plain)
                    arm["profiled_distribution"] = distribution(profiled)
                    arm["same_backend_parity"] = all(all(matched_differences(a,b)["match"] for a,b in zip(traces[0],x)) for x in traces)
                    if backend == "ocv":
                        references[n] = traces[0]
                    arm["reference_nonempty"] = any(references[n])
                    arm["cross_backend_differences"] = [matched_differences(a,b) for a,b in zip(references[n],traces[0])]
                    if not arm["same_backend_parity"] or not all(x["match"] for x in arm["cross_backend_differences"]):
                        raise ValueError("synthetic smoke mismatch")
                    save(output/f"arm-{backend}{n}.json", arm)
            # Six malformed messages per backend pair at minimum feasible threads:
            # original plain worker and instrumented adapter, no retry.
            n = threads_list[0]
            for backend in ("ocv","ort"):
                for mode in ("plain","profile"):
                    for name,payload in (("invalid_jpeg", LENGTH.pack(4)+b"bad!"),
                                         ("zero_length", LENGTH.pack(0)),
                                         ("truncated", LENGTH.pack(5)+b"x")):
                        result = await asyncio.to_thread(negative_ipc,spec,root,backend,n,mode,payload)
                        report["negative_ipc"].append(dict(backend=backend,threads=n,mode=mode,case=name,**result))
                        if not result["passed"]:
                            raise ValueError("negative IPC did not fail closed")
            report["complete"] = True
            report["all_overhead_gates"] = all(x["overhead"]["pass_gate"] for x in report["arms"])
            report["decision"] = "TECHNICAL_PREFLIGHT_COMPLETE" if report["all_overhead_gates"] else "TECHNICAL_PREFLIGHT_OVERHEAD_FAIL"
    except Exception as exc:
        report["decision"] = "INCOMPLETE"
        report["error"] = type(exc).__name__+":"+str(exc)[:200]
        raise
    finally:
        save(output/"preflight-ipc.json",report)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plain-worker",nargs=2)
    for k in ("model-spec","model-root","output"):
        parser.add_argument("--"+k,type=Path)
    a = parser.parse_args()
    if a.plain_worker:
        return plain_child(a.plain_worker[0],int(a.plain_worker[1]))
    import platform, cv2, numpy as np, onnxruntime as ort
    if sys.version_info[:2] != (3,12) or platform.system() != "Linux" or platform.machine() != "x86_64" or (cv2.__version__,np.__version__,ort.__version__) != ("4.11.0","2.2.6","1.22.0"):
        parser.error("target environment mismatch")
    if not all((a.model_spec,a.model_root,a.output)) or not a.output.is_dir():
        parser.error("missing private input/output")
    spec = ModelSpec.model_validate_json(a.model_spec.read_text())
    asyncio.run(run(spec,a.model_root,a.output))
    return 0

if __name__ == "__main__":
    sys.exit(main())
