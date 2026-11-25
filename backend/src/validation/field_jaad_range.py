"""Bounded read-only official JAAD ZIP range acquisition; no full archive fallback."""
import argparse
import hashlib
import io
import os
from pathlib import Path,PurePosixPath
import re
import urllib.request
import zipfile
from src.validation.field_readiness import (MIB,BLOBS,CLIPS,REVISION,read_reference,require,ref,read,private_path,write,result)

URL="https://data.nvision2.eecs.yorku.ca/JAAD_dataset/data/JAAD_clips.zip"
BUDGET=256*MIB
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

class RangeFile(io.RawIOBase):
    def __init__(self,client=None,budget=BUDGET):
        super().__init__();self.client=client or opener();self.budget=budget;self.transferred=0;self.pos=0;self.etag=None;self.size=None
        self.fetch(0,0)
    def fetch(self,start,end):
        n=end-start+1;require(0<n<=8*MIB and self.transferred+n<=self.budget,"transfer budget")
        headers={"Range":f"bytes={start}-{end}","Accept-Encoding":"identity"}
        if self.etag:headers["If-Match"]=self.etag
        with self.client.open(urllib.request.Request(URL,headers=headers),timeout=30) as r:
            require(r.status==206 and r.geturl()==URL,"exact official partial response required")
            match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",r.headers.get("Content-Range",""))
            require(match is not None,"invalid Content-Range")
            a,b,total=map(int,match.groups());tag=r.headers.get("ETag","")
            require((a,b)==(start,end) and end<total and re.fullmatch(r'"[^"\r\n]+"',tag) is not None
                    and r.headers.get("Content-Encoding","identity")=="identity","invalid range or strong validator")
            require(self.size is None or (self.size==total and self.etag==tag),"archive identity changed")
            self.size=total;self.etag=tag
            require(r.headers.get("Content-Length")==str(n),"exact response length header required")
            raw=r.read(n);self.transferred+=len(raw)
            require(len(raw)==n and self.transferred<=self.budget,"invalid response length")
            return raw
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        p=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset if whence==2 else -1
        require(0<=p<=self.size,"invalid seek");self.pos=p;return p
    def read(self,n=-1):
        n=self.size-self.pos if n<0 else min(n,self.size-self.pos)
        require(n<=self.budget-self.transferred,"transfer budget")
        parts=[]
        while n:
            k=min(n,8*MIB);parts.append(self.fetch(self.pos,self.pos+k-1));self.pos+=k;n-=k
        return b"".join(parts)

def select(z):
    selected={}
    for info in z.infolist():
        name=PurePosixPath(info.filename)
        if name.name not in {c+".mp4" for c in CLIPS}:continue
        require(name.stem not in selected and not name.is_absolute() and ".." not in name.parts and "\\" not in info.filename
                and not info.is_dir() and not info.flag_bits&1 and (info.external_attr>>16)&0o170000!=0o120000,"unsafe or duplicate member")
        require(0<info.file_size<=128*MIB,"clip limit");selected[name.stem]=info
    require(set(selected)==set(CLIPS) and sum(x.file_size for x in selected.values())<=256*MIB,"selection limit")
    return selected

def acquire(receipt,xml_dir,output,client=None):
    require(receipt.get("origin")=="official_jaad_2_0" and receipt.get("revision")==REVISION
        and receipt.get("video_license")=="CC BY 4.0" and receipt.get("source_url")==URL
        and all(ref(receipt.get(k)) for k in ("provenance_ref","authorization_ref","license_review_ref","attribution_ref")),"approved receipt required")
    root=private_path(output);require(not root.exists(),"output exists")
    refs={}
    for clip in CLIPS:
        d=read_reference(Path(xml_dir)/(clip+".xml"),clip,BLOBS[clip])
        refs[clip]={"xml_sha256":d["xml_sha256"],"xml_git_blob":BLOBS[clip],"annotation_size":d["size"],"annotation_width":d["width"],"annotation_height":d["height"]}
    with RangeFile(client) as remote,zipfile.ZipFile(remote) as z:
        selected=select(z);root.mkdir(mode=0o700,exist_ok=False)
        for clip,info in sorted(selected.items()):
            h=hashlib.sha256();n=0
            with z.open(info) as src,os.fdopen(os.open(root/(clip+".mp4"),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb") as dst:
                for chunk in iter(lambda:src.read(MIB),b""):
                    n+=len(chunk);require(n<=info.file_size,"expanded size");h.update(chunk);dst.write(chunk)
            require(n==info.file_size,"member mismatch");refs[clip].update(video_sha256=h.hexdigest(),video_bytes=n)
        report=result("private_partial_jaad_acquisition_not_evaluation",source_url=URL,archive_etag=remote.etag,
           archive_size=remote.size,archive_sha256=None,transferred_bytes=remote.transferred,
           receipt_sha256=hashlib.sha256(__import__("json").dumps(receipt,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest(),
           clips=refs,origin_authenticated=False,alignment_review="PENDING")
        write(root/"import-report.json",report);return report

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",required=True);p.add_argument("--xml-directory",required=True);p.add_argument("--directory",required=True);a=p.parse_args()
    acquire(read(a.receipt),a.xml_directory,a.directory)
if __name__=="__main__":main()
