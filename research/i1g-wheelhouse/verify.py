"""Verify the frozen I1G inventory without installing or importing its packages."""
import base64
import csv
import hashlib
import io
import json
import platform
import sys
import sysconfig
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

try:
    from packaging.tags import sys_tags
    from packaging.utils import canonicalize_name, parse_wheel_filename
    from packaging.specifiers import SpecifierSet
    from packaging.requirements import Requirement
except ImportError:
    from pip._vendor.packaging.tags import sys_tags
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.requirements import Requirement

TAGS = set(sys_tags())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_record(archive, info):
    paths = [e.filename for e in archive.infolist() if not e.is_dir()]
    require(len(paths) == len(set(paths)), "duplicate ZIP member")
    record = info + "/RECORD"
    rows = csv.reader(io.StringIO(archive.read(record).decode("utf-8")))
    seen = set()
    for path, digest, size in rows:
        require(path not in seen, "duplicate RECORD entry " + path)
        seen.add(path)
        if path == record:
            require(not digest and not size, "invalid self digest")
            continue
        algo, expected = digest.split("=", 1)
        require(algo in {"sha256", "sha384", "sha512"}, "weak RECORD digest")
        with archive.open(path) as stream:
            actual = hashlib.file_digest(stream, algo).digest()
        encoded = base64.urlsafe_b64encode(actual).rstrip(b"=").decode()
        require(encoded == expected and archive.getinfo(path).file_size == int(size),
                "RECORD mismatch " + path)
    require(seen == set(paths) - {record + ".jws", record + ".p7s"}, "RECORD coverage")


def verify(row, directory):
    name, version, filename, digest = (row[k] for k in ("name", "version", "wheel", "sha256"))
    parsed_name, parsed_version, _, tags = parse_wheel_filename(filename)
    require(parsed_name == canonicalize_name(name) and str(parsed_version) == version
            and tags & TAGS, "filename or platform mismatch")
    with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=20) as response:
        files = json.load(response)["urls"]
    entry, = [f for f in files if f["filename"] == filename]
    require(entry["digests"]["sha256"] == digest, "PyPI SHA256 mismatch")
    url = urlsplit(entry["url"])
    require((url.scheme, url.netloc) == ("https", "files.pythonhosted.org"), "unexpected origin")
    target = directory / filename
    with urlopen(url.geturl(), timeout=30) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    with target.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == digest, "download SHA256 mismatch")
    with zipfile.ZipFile(target) as archive:
        meta, = [p for p in archive.namelist() if p.endswith(".dist-info/METADATA")]
        check_record(archive, meta.rsplit("/", 1)[0])
        msg = BytesParser().parsebytes(archive.read(meta))
        require(canonicalize_name(msg["Name"]) == parsed_name and msg["Version"] == version,
                "METADATA identity mismatch")
        require(platform.python_version() in SpecifierSet(msg.get("Requires-Python", "")),
                "incompatible Requires-Python")
        return [Requirement(s) for s in msg.get_all("Requires-Dist", [])]


def closure(rows, dependencies):
    pins = {canonicalize_name(r["name"]): r["version"] for r in rows}
    todo = [(name, "") for name in pins] + [("psycopg", "binary")]
    seen = set()
    while todo:
        name, extra = todo.pop()
        if (name, extra) in seen:
            continue
        seen.add((name, extra))
        for req in dependencies[name]:
            if req.marker and not req.marker.evaluate({"extra": extra}):
                continue
            key = canonicalize_name(req.name)
            require(not req.url and key in pins and pins[key] in req.specifier,
                    f"{name}[{extra}] requires {req}, inventory has {pins.get(key)}")
            todo.extend((key, e) for e in req.extras)


def main():
    require(sys.version_info[:2] == (3, 12) and sysconfig.get_platform() == "linux-x86_64",
            "requires CPython 3.12 Linux x86_64")
    print(sys.version, platform.platform(), flush=True)
    data = Path(__file__).with_name("inventory.json").read_bytes()
    require(hashlib.sha256(data).hexdigest() == "b68cf5f7719a531192ac9c12f0303822412eaac36320e800e83fb85afbf79777",
            "frozen inventory changed")
    rows = json.loads(data)
    deps = {}
    with tempfile.TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(r, pool.submit(verify, r, Path(directory))) for r in rows]
        for row, future in futures:
            try:
                deps[canonicalize_name(row["name"])] = future.result()
                print("VERIFIED", row["wheel"], row["sha256"], flush=True)
            except Exception as exc:
                print("BLOCKED", row["wheel"], type(exc).__name__, str(exc), flush=True)
    print(f"Verified {len(deps)}/{len(rows)} wheels", flush=True)
    require(len(deps) == len(rows), "dependency closure pending")
    closure(rows, deps)
    print("I1G WHEELHOUSE LOCK VERIFIED")
    for r in rows:
        extra = "[binary]" if r["name"] == "psycopg" else ""
        print(f"{r['name']}{extra}=={r['version']} --hash=sha256:{r['sha256']}")


if __name__ == "__main__":
    main()
