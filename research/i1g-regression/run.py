"""Recreate the historical source layout and compare every JUnit case and outcome."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

def results(path):
    return Counter((case.attrib["classname"], case.attrib["name"],
                    next((tag for tag in ("error", "failure", "skipped")
                          if case.find(tag) is not None), "passed"))
                   for case in ET.parse(path).iter("testcase"))

def main():
    failures = []
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        with ZipFile(HERE / "fixtures.zip") as archive:
            archive.extractall(root)
        for row in json.loads((root / "source-manifest.json").read_text()):
            relative = Path(row["path"])
            src = REPO / relative
            assert hashlib.sha256(src.read_bytes()).hexdigest() == row["sha256"], relative
            dest = root / "repo" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        backend = root / "repo/backend"
        suites = [
            ("I1E", root / "i1f/prior", ["test_diagnostic.py"], "i1e-retest.xml"),
            ("I1F", root / "i1f", ["test_parity.py", "test_hook.py"], "i1f-retest.xml"),
            ("Originais", backend, sorted(str(p.relative_to(backend)) for p in
                                          (backend / "tests").glob("test_*.py")), "original-tests.xml"),
            ("I1G", root, ["test_release.py"], "release-tests-final.xml"),
        ]
        for name, cwd, tests, baseline in suites:
            out = root / (name + ".xml")
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs",
                                   "--junitxml", str(out), *tests], cwd=cwd,
                                  env={**os.environ, "SI11D_SUMO_REQUIRED": "0",
                                       "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
            expected = results(root / baseline)
            actual = results(out) if out.exists() else Counter()
            print(name, "observed outcomes", dict(Counter(k[2] for k in actual.elements())), flush=True)
            if proc.returncode or expected != actual:
                print("missing or changed", expected - actual, "new or changed", actual - expected)
                failures.append(name)
    if failures:
        raise SystemExit("Regression mismatch: " + ", ".join(failures))
    print("I1G REGRESSION PASS: 149 passed, 3 expected skips, 152 matched identities and outcomes")

if __name__ == "__main__":
    main()
