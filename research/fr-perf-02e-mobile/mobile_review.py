"""Same-host review component. No acquisition or inference at import/start.
Integration must supply actual fixture, source, private-host and observation adapters.
Never use this component as proof of legal approval or actual viewing.
"""
import hashlib, html, json, os, re, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

class Review:
    def __init__(self, root, fixture_check, private_check, acquire, verify, observe, *, ttl=600):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_relative_to(Path('/tmp')) or self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077:
            raise ValueError('private workspace required')
        self.fixture_check, self.private_check = fixture_check, private_check
        self.acquire, self.verify, self.observe = acquire, verify, observe
        self.ttl = ttl
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.state, self.digest, self.proof, self.review = 'WAITING', None, None, None
        self.media = self.root / 'original.webm'
        self.deadline = 0
    def cleanup(self):
        self.media.unlink(missing_ok=True)
    def check(self):
        try: private = self.private_check()
        except Exception: private = False
        if private is not True:
            self.cleanup(); self.state = 'BLOCKED'; raise ValueError('private port not verified')
        if self.state == 'REVIEW' and time.monotonic() >= self.deadline:
            self.cleanup(); self.state = 'EXPIRED'; raise ValueError('review expired')
    def start(self, plan):
        with self.lock:
            self.check()
            if plan != 'yes': raise ValueError('explicit restricted-processing plan required')
            if self.state != 'WAITING' or self.media.exists(): raise ValueError('one acquisition only')
            self.state = 'PREPARING'
            try:
                self.proof = self.fixture_check()
                if not isinstance(self.proof, str) or not re.fullmatch('[0-9a-f]{64}', self.proof): raise ValueError('fixture proof required')
                self.check()
                self.acquire(self.media)
                if self.media.is_symlink() or not self.media.is_file() or self.media.stat().st_mode & 0o077: raise ValueError('private media required')
                self.digest = self.verify(self.media)
                if not isinstance(self.digest, str) or not re.fullmatch('[0-9a-f]{64}', self.digest): raise ValueError('source digest required')
                self.deadline = time.monotonic()+self.ttl; self.state = 'REVIEW'
                self.check()
            except BaseException:
                self.cleanup(); self.state = 'BLOCKED'; raise
    def decide(self, decision, checked, reason):
        with self.lock:
            self.check()
            if self.state != 'REVIEW': raise ValueError('review not ready')
            if decision not in ('approve','reject'): raise ValueError('explicit decision required')
            if decision == 'reject': self.cleanup(); self.state = 'REJECTED'; return
            if checked != 'yes' or not 20 <= len(reason.strip()) <= 500: raise ValueError('explicit review and reason required')
            self.review = dict(source_sha256=self.digest, fixture_proof_sha256=self.proof, decision='RESTRICTED_PROCESSING_APPROVED', reviewed_by_human_declared=True, reason=reason.strip(), timestamp=int(time.time()))
            try:
                if self.verify(self.media) != self.digest or self.fixture_check() != self.proof: raise ValueError('identity changed')
                self.check(); self.state = 'OBSERVING'
                self.observe(self.media, self.review)
                self.state = 'COMPLETE'
            except BaseException:
                self.state = 'FAILED'; raise
            finally: self.cleanup()
    def page(self):
        t=html.escape(self.token); status=html.escape(self.state)
        body=f'<h1>Revisão privada</h1><p>Estado: <strong>{status}</strong></p>'
        if self.state=='WAITING': body+=f'<form method="post" action="/start"><input type="hidden" name="token" value="{t}"><label><input type="checkbox" name="plan" value="yes"> Autorizo a aquisição única para revisão e tratamento restrito neste ambiente privado, sem identificação, exportação ou retenção após o ensaio.</label><button>Validar pré-requisitos e preparar vídeo</button></form>'
        if self.state=='REVIEW':
            body+=f'<p>SHA-256: <code>{self.digest}</code></p><video controls playsinline preload="none" src="/media"></video><p>Assista ao trecho integral. Se não puder reproduzir ou avaliar, rejeite. Não registre placas, nomes ou outros identificadores.</p><form method="post" action="/decision"><input type="hidden" name="token" value="{t}"><label><input type="checkbox" name="checked" value="yes"> Revisei o conteúdo integral e autorizo o tratamento restrito, sem identificação ou exportação.</label><label>Fundamentação sem dados pessoais<textarea name="reason" maxlength="500"></textarea></label><button name="decision" value="approve">Aprovar tratamento restrito e observar</button><button name="decision" value="reject" formnovalidate>Rejeitar ou interromper</button></form>'
        return ('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisão privada</title><style>body{font:17px system-ui;max-width:640px;margin:24px auto;padding:0 16px;color:#17202a}button,textarea{font:inherit;width:100%;box-sizing:border-box;margin:12px 0;padding:14px}video{width:100%;background:#111}code{overflow-wrap:anywhere}label{display:block;margin:16px 0}</style>'+body+'</html>').encode()

def serve(session, origin, port=8787):
    if not re.fullmatch(r'https://[a-z0-9-]+-\d+\.app\.github\.dev',origin): raise ValueError('exact Codespace origin required')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,data,kind='text/plain; charset=utf-8',extra=()):
            self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; form-action 'self'; frame-ancestors 'none'")
            for k,v in extra:self.send_header(k,v)
            self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            try:
                with session.lock:
                    session.check()
                    if self.path=='/':return self.send(200,session.page(),'text/html; charset=utf-8')
                    if self.path!='/media' or session.state!='REVIEW':return self.send(404,b'Unavailable')
                    raw=session.media.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=session.digest:session.cleanup();session.state='BLOCKED';raise ValueError('changed media')
                    n=len(raw); r=self.headers.get('Range')
                    if r:
                        m=re.fullmatch(r'bytes=(\d+)-(\d*)',r)
                        if not m:return self.send(416,b'',extra=(('Content-Range',f'bytes */{n}'),))
                        lo=int(m[1]); hi=min(int(m[2]) if m[2] else n-1,n-1)
                        if lo>hi:return self.send(416,b'',extra=(('Content-Range',f'bytes */{n}'),))
                        return self.send(206,raw[lo:hi+1],'video/webm',(('Accept-Ranges','bytes'),('Content-Range',f'bytes {lo}-{hi}/{n}')))
                    return self.send(200,raw,'video/webm',(('Accept-Ranges','bytes'),))
            except Exception:self.send(403,b'Blocked')
        def do_POST(self):
            try:
                if self.headers.get('Origin')!=origin or self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded':raise ValueError('origin')
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=4096:raise ValueError('length')
                d=parse_qs(self.rfile.read(n).decode(),max_num_fields=5)
                if not secrets.compare_digest(d.get('token',[''])[0],session.token):raise ValueError('token')
                if self.path=='/start':session.start(d.get('plan',[''])[0])
                elif self.path=='/decision':session.decide(d.get('decision',[''])[0],d.get('checked',[''])[0],d.get('reason',[''])[0])
                else:raise ValueError('path')
                self.send(303,b'',extra=(('Location','/'),))
            except Exception:self.send(403,b'Blocked or incomplete review; return to the private page.')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.timeout=1;server.daemon_threads=False
    waiting_deadline=time.monotonic()+300
    try:
        while session.state not in ('COMPLETE','REJECTED','FAILED','BLOCKED','EXPIRED'):
            server.handle_request()
            with session.lock:
                if session.state=='WAITING':
                    if time.monotonic()>=waiting_deadline:session.state='EXPIRED'
                elif session.state=='REVIEW' and time.monotonic()>=session.deadline:
                    session.cleanup();session.state='EXPIRED'
    finally:
        server.server_close();session.cleanup()
