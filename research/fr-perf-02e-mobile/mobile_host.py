"""Codespace same-host adapter, experimental observation only. No Actions dispatch.
Run only via the frozen branch bootstrap; source transfer is gated by real fixtures
and the authenticated private-port review. No Bellevue paths are opened.
"""
import argparse, asyncio, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree
from mobile_review import Review, serve

REPO='LucaSoares87/sem-foro_inteligente'
OWNER=218621709
PORT=8787
BRANCH='research/fr-perf-02e-mobile'

def gh_json(*args):
    return json.loads(subprocess.check_output(['gh',*args],timeout=12,stderr=subprocess.DEVNULL))

def host_identity():
    name=os.environ.get('CODESPACE_NAME','')
    if os.environ.get('CODESPACES')!='true' or not re.fullmatch('[a-z0-9-]{1,120}',name):raise ValueError('Codespace required')
    u=gh_json('api','user');s=gh_json('api','user/codespaces/'+name)
    if u.get('id')!=OWNER or s.get('name')!=name or s.get('owner',{}).get('id')!=OWNER or s.get('repository',{}).get('full_name')!=REPO or s.get('state')!='Available':raise ValueError('authenticated owner and Codespace required')
    return name

def private_port(name):
    try:
        if host_identity()!=name:return False
        rows=gh_json('codespace','ports','-c',name,'--json','sourcePort,visibility,browseUrl')
        match=[p for p in rows if p.get('sourcePort')==PORT]
        return len(match)==1 and match[0].get('visibility','').lower()=='private' and match[0].get('browseUrl','').rstrip('/')==f'https://{name}-{PORT}.app.github.dev'
    except Exception:return False

def junit_count(path):
    t=ElementTree.parse(path).getroot();s=[t] if t.tag=='testsuite' else t.findall('testsuite')
    n=sum(int(x.attrib['tests']) for x in s)
    if n<107 or any(int(x.attrib.get(k,0)) for x in s for k in ('failures','errors','skipped')):raise ValueError('fixture regression incomplete')
    return n

def runtime(a):
    from src.benchmarking import fr_perf_02c as c,fr_perf_02e_obs_r as r
    from src.vision.contracts import ModelSpec
    from src.benchmarking.si10_cpu_profile import cpu_budget
    if sys.version_info[:3]!=(3,12,16):raise ValueError('exact Python version required')
    c.verify_environment(a.root/'research/fr-perf-02c/requirements.lock');c.verify_acquisition_lock(a.root/'research/fr-perf-02c/acquisition.lock')
    r.frozen(a.root/'evidence');r.verify_source_contract()
    spec=ModelSpec.model_validate_json((a.runtime/'model/yolox_s.model-spec.json').read_text())
    if spec.sha256!=c.MODEL or spec.purpose!='validation_only' or spec.architecture!='yolox' or (spec.confidence,spec.nms_iou)!=(.25,.45) or c.digest(spec.resolve(a.runtime/'model').read_bytes())!=c.MODEL:raise ValueError('model identity')
    if cpu_budget()['thread_budget']<2:raise ValueError('insufficient CPU')
    return c,r,spec,cpu_budget()

def context(a):
    c,r,spec,hw=runtime(a)
    return dict(commit=a.commit,host=host_identity(),cpu_budget=hw,environment=c.runtime_info(),model_sha256=c.MODEL,lock_sha256=c.LOCK_SHA256,acquisition_lock_sha256=c.ACQUISITION_LOCK_SHA256,oracles=r.FIXED,adendum=r.ADENDUM,protocol_sha256=c.digest((a.root/'research/fr-perf-02e-mobile/PROTOCOL-MOBILE.md').read_bytes()))

async def real_fixtures(a):
    from src.benchmarking.fr_perf_01a import synthetic_frames
    import numpy as np
    c,r,spec,hw=runtime(a);ctx=context(a);n=junit_count(a.evidence/'fixtures.xml')
    src=synthetic_frames();frames=[src[k] for k in c.SLOTS[:4]];del src
    hashes=[c.digest(x) for x in frames]
    if hashes!=c.load_inputs(a.root/'research/fr-perf-02c/input-hashes.json')['synthetic'][:4]:raise ValueError('fixture frame identity')
    # Additional true worker smoke using the authorized transformation.
    img=np.zeros((1080,1920,3),dtype=np.uint8);jpeg,resize=r.transform(img)
    frames.append(jpeg);hashes.append(c.digest(jpeg))
    report=dict(scope='mobile_same_host_fixtures',context=ctx,tests=n,junit_sha256=c.digest((a.evidence/'fixtures.xml').read_bytes()),resize=resize,arms=[],passed=False,**r.FLAGS)
    try:
        async with asyncio.timeout(110):
            for backend in ('ocv','ort'):
                arm=dict(backend=backend,threads=2,blocks=[],plain_profile_parity=False);report['arms'].append(arm);out=[]
                for profile in (False,True):
                    rows=[];arm['blocks'].append(dict(profile=profile,rows=rows));ds,cpu,parent=await c.block(spec,a.runtime/'model',backend,2,frames,profile,rows)
                    c.verify_rows(rows,hashes);out.append(ds);arm['blocks'][-1].update(cpu=cpu,parent_cpu=parent)
                arm['plain_profile_parity']=all(c.matched_differences(x,y)['match'] for x,y in zip(*out)) and len(out[0])==len(out[1])==5
                if not arm['plain_profile_parity']:raise ValueError('plain/profile mismatch')
        report['passed']=True
    except BaseException as e:
        report['error_type']=type(e).__name__;raise
    finally:c.save(a.evidence/'fixture-proof.json',report)

class Host:
    def __init__(self,a):
        self.a=a;self.c,self.r,self.spec,_=runtime(a);self.ctx=context(a);self.name=self.ctx['host'];self.media_hash=None;self.manifest=None;self.transfer_started=None
        self.proof_path=a.evidence/'fixture-proof.json';self.proof_hash=self.c.digest(self.proof_path.read_bytes())
        self.check_fixture()
    def check_fixture(self):
        c,r=self.c,self.r;p=r.read_proof(self.proof_path)
        if self.c.digest(self.proof_path.read_bytes())!=self.proof_hash or p.get('scope')!='mobile_same_host_fixtures' or p.get('context')!=context(self.a) or p.get('passed') is not True or p.get('tests')!=junit_count(self.a.evidence/'fixtures.xml') or p.get('junit_sha256')!=c.digest((self.a.evidence/'fixtures.xml').read_bytes()) or any(p.get(k)!=v for k,v in r.FLAGS.items()):raise ValueError('same-host fixture identity')
        expected=c.load_inputs(self.a.root/'research/fr-perf-02c/input-hashes.json')['synthetic'][:4]+[p['resize']['jpeg_sha256']]
        if [(x['backend'],x['threads']) for x in p['arms']]!=[('ocv',2),('ort',2)]:raise ValueError('fixture arms')
        for arm in p['arms']:
            if arm['plain_profile_parity'] is not True or [b['profile'] for b in arm['blocks']]!=[False,True]:raise ValueError('fixture parity')
            for b in arm['blocks']:c.verify_rows(b['rows'],expected)
        return self.proof_hash
    def private(self):return private_port(self.name)
    def verify(self,path):return self.r.verify_bytes(path.read_bytes())
    def acquire(self,path):
        self.check_fixture()
        if not self.private() or self.transfer_started is not None:raise ValueError('private single acquisition gate')
        self.transfer_started=time.monotonic();r=self.r
        q=urlencode(dict(action='query',revids=r.REVISION,prop='revisions|imageinfo',rvprop='ids',iiprop='url|sha1|size|mime|extmetadata',format='json',formatversion=2))
        meta=r.verify_metadata(json.loads(r.fetch('https://commons.wikimedia.org/w/api.php?'+q,1024*1024)))
        raw=r.fetch(r.URL,15*1024*1024,90);self.media_hash=r.verify_bytes(raw)
        with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as f:f.write(raw)
        frames,records=r.decode(path);r.verify_manifest(frames,records);self.manifest=records;del frames
        self.acquisition_seconds=time.monotonic()-self.transfer_started
        if self.acquisition_seconds>180:raise TimeoutError('acquisition plus cadence cap')
        self.c.save(self.a.evidence/'source-proof.json',dict(scope='same_host_source_verified',sha256=self.media_hash,metadata=meta,records=records,fixture_proof_sha256=self.proof_hash,**r.FLAGS))
    def observe(self,path,review):
        self.check_fixture()
        if not self.private() or self.verify(path)!=self.media_hash or review['source_sha256']!=self.media_hash or review['fixture_proof_sha256']!=self.proof_hash:raise ValueError('review/source binding')
        # Private proof contains the reviewer's own declaration, never a claim of legal certification.
        self.c.save(self.a.evidence/'review-private.json',dict(**review,reviewer_account_id=OWNER,context=self.ctx))
        asyncio.run(self._observe(path))
    async def _observe(self,path):
        c,r=self.c,self.r;out=self.a.evidence;frames,records=r.decode(path)
        if records!=self.manifest:raise ValueError('decoded source changed')
        hashes=r.verify_manifest(frames,records);outputs=[]
        report=dict(scope='mobile_observation_only',context=self.ctx,fixture_proof_sha256=self.proof_hash,source_sha256=self.media_hash,review_sha256=c.digest((out/'review-private.json').read_bytes()),blocks=[],pairs=[],determinism=[],complete=False,**r.FLAGS)
        try:
            async with asyncio.timeout(min(465,900-self.acquisition_seconds)):
                for i,b in enumerate(r.SCHEDULE):
                    if not self.private() or self.verify(path)!=self.media_hash or r.verify_manifest(frames,records)!=hashes:raise ValueError('input or private gate changed')
                    rows=[];block=dict(index=i,backend=b,threads=2,rows=rows,complete=False);report['blocks'].append(block)
                    try:
                        ds,cpu,parent=await c.block(self.spec,self.a.runtime/'model',b,2,frames,False,rows);c.verify_rows(rows,hashes);outputs.append(ds)
                        block.update(complete=True,cpu_per_frame=cpu,parent_cpu_per_frame=parent,detector=c.distribution([x['inference_ms'] for x in rows]),ipc=c.distribution([x['ipc_roundtrip_ms'] for x in rows]))
                    finally:c.save(out/f'block-{i}.json',block)
                for i,j in ((0,1),(3,2)):report['pairs'].append(dict(reference_block=i,candidate_block=j,**r.compare(outputs[i],outputs[j],self.spec)))
                for i,j in ((0,3),(1,2)):report['determinism'].append(dict(reference_block=i,candidate_block=j,detection_hashes_equal=[x['detection_hash'] for x in report['blocks'][i]['rows']]==[x['detection_hash'] for x in report['blocks'][j]['rows']],**r.compare(outputs[i],outputs[j],self.spec)))
                report['complete']=True;report['decision']='OBSERVATION_COMPLETE_NO_SELECTION'
        except BaseException as e:report['error_type']=type(e).__name__;report['decision']='INCOMPLETE';raise
        finally:c.save(out/'observation.json',report)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('host-check','fixtures','review'))
    for k in ('root','runtime','evidence'):p.add_argument('--'+k,type=Path)
    p.add_argument('--commit');a=p.parse_args();os.umask(0o077)
    if a.mode=='host-check':print(host_identity());return
    if not a.commit or not re.fullmatch('[a-f0-9]{40}',a.commit):raise ValueError('commit required')
    if a.mode=='fixtures':asyncio.run(real_fixtures(a));return
    h=Host(a);root=a.runtime/'review-media';root.mkdir(mode=0o700,exist_ok=False)
    session=Review(root,h.check_fixture,h.private,h.acquire,h.verify,h.observe)
    print(f'http://127.0.0.1:{PORT}',flush=True)
    print(f'Abra a porta {PORT} como Private e use https://{h.name}-{PORT}.app.github.dev',flush=True)
    serve(session,f'https://{h.name}-{PORT}.app.github.dev',PORT)
    print('Final:',session.state,flush=True)
if __name__=='__main__':main()
