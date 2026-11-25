"""Verify the preserved historical package without extracting or altering originals."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path,index):
    index=json.loads(Path(index).read_text(encoding="utf-8"))
    if digest(path)!=index["archive_sha256"]:
        raise ValueError("outer archive hash mismatch")
    expected={x["filename"]:x["sha256"] for x in index["files"]}
    if len(expected)!=14 or index["physical_actuation"] or index["field_approval"]:
        raise ValueError("unexpected index")
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!={"manifest.json","LEIA-ME.txt"}|{"originais/"+n for n in expected}:
            raise ValueError("archive member mismatch")
        for name,sha in expected.items():
            h=hashlib.sha256()
            with archive.open("originais/"+name) as f:
                for chunk in iter(lambda:f.read(1024*1024),b""):
                    h.update(chunk)
            if h.hexdigest()!=sha:
                raise ValueError("original hash mismatch: "+name)
    return {"verified_originals":len(expected),"archive_sha256":index["archive_sha256"],"field_approval":False}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("archive")
    p.add_argument("--index",default="docs/si13/evidence-index.json")
    a=p.parse_args()
    print(json.dumps(verify(a.archive,a.index),sort_keys=True))
