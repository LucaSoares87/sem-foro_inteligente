"""Generate a private, offline blind C3 annotation bundle from frozen pixels."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import cv2
from src.validation.field_readiness import private_path,require,read,ref
from src.validation.io import sha256_file
from src.benchmarking.pimcat_c3_study import COMMON,FRAMES,blank_reference

def frames(video,preflight):
    require(preflight["frames"]==FRAMES and preflight["fps"]==30
            and sha256_file(video)==preflight["derived_sha256"],"frozen clip mismatch")
    cap=cv2.VideoCapture(str(video));h=hashlib.sha256();images=[]
    try:
        require(cap.isOpened() and abs(cap.get(cv2.CAP_PROP_FPS)-30)<.001,"invalid clip FPS")
        for i in range(1,FRAMES+1):
            ok,img=cap.read();require(ok and img.shape==(720,1280,3),"invalid frozen frame")
            h.update(img.tobytes())
            if i in COMMON:
                ok,png=cv2.imencode(".png",img);require(ok,"PNG encoding failed")
                images.append(base64.b64encode(png.tobytes()).decode("ascii"))
        require(not cap.read()[0],"extra frames")
    finally:cap.release()
    require(h.hexdigest()==preflight["decoded_pixel_sha256"] and len(images)==40,"pixel hash mismatch")
    return images

def render(preflight,images):
    require(len(images)==len(COMMON),"incomplete bundle")
    payload=json.dumps({"reference":blank_reference(preflight["decoded_pixel_sha256"]),"images":images},separators=(",",":")).replace("<","\\u003c")
    template=Path(__file__).with_name("field_annotation.html").read_text(encoding="utf-8")
    require(template.count("__PRIVATE_PAYLOAD__")==1,"template mismatch")
    return template.replace("__PRIVATE_PAYLOAD__",payload)

def prepare(video,preflight,output,authorization):
    require(ref(authorization),"private media authorization required")
    images=frames(video,preflight);html=render(preflight,images)
    require(len(html.encode())<=128*1024*1024,"bundle size limit")
    root=private_path(output);root.mkdir(mode=0o700,exist_ok=False)
    for key in ("a","b"):
        folder=root/key;folder.mkdir(mode=0o700)
        with os.fdopen(os.open(folder/"annotation.html",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),"w",encoding="utf-8") as f:f.write(html)

def main():
    p=argparse.ArgumentParser();p.add_argument("--video",required=True);p.add_argument("--preflight",required=True);p.add_argument("--directory",required=True);p.add_argument("--authorization-ref",required=True);a=p.parse_args()
    prepare(a.video,read(a.preflight),a.directory,a.authorization_ref)
if __name__=="__main__":main()
