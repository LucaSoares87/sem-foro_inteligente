"""Run only the historical original tests and the independent parity replay."""
import base64
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import hashlib
import json
import shutil
from run import HERE, REPO, results


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with ZipFile(HERE / "fixtures.zip") as archive:
            archive.extractall(root)
        for row in json.loads((root / "source-manifest.json").read_text()):
            src = REPO / row["path"]
            assert hashlib.sha256(src.read_bytes()).hexdigest() == row["sha256"], src
            dest = root / "repo" / row["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)

        backend = root / "repo/backend"
        tests = sorted(str(p.relative_to(backend)) for p in (backend / "tests").glob("test_*.py"))
        junit = root / "target-original.xml"
        run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-ra", "--junitxml", str(junit), *tests],
                             cwd=backend, env={**os.environ, "SI11D_SUMO_REQUIRED": "1",
                                               "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        reference = results(root / "original-tests.xml")
        target = Counter((module, name, "passed") for module, name, _ in reference.elements())
        observed = results(junit) if junit.exists() else Counter()
        originals_ok = run.returncode == 0 and sum(target.values()) == 49 and target == observed
        print("Original outcomes:", dict(Counter(k[2] for k in observed.elements())), flush=True)

        parity = root / "target-parity.json"
        replay = subprocess.run([sys.executable, "real_parity.py", "--output", str(parity)], cwd=root)
        # Retain the two original outputs in the job log, including partial results.
        receipt = root / "evidence.zip"
        with ZipFile(receipt, "w", ZIP_DEFLATED) as bundle:
            for path in (junit, parity):
                if path.exists():
                    bundle.write(path, path.name)
        data = receipt.read_bytes()
        print("I1G_EVIDENCE_SHA256", hashlib.sha256(data).hexdigest())
        for i in range(0, len(data), 3000):
            print("I1G_EVIDENCE_DATA", base64.b64encode(data[i:i+3000]).decode())
        if not originals_ok or replay.returncode:
            raise SystemExit(f"Original suite OK={originals_ok}, parity exit={replay.returncode}")
        print("I1G SUMO AND PARITY PASS")


if __name__ == "__main__":
    main()
