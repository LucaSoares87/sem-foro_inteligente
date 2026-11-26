import hashlib, tempfile, os
from pathlib import Path
import pytest
from mobile_review import Review

def make(tmp, fixture=True, private=True):
    root=Path(tempfile.mkdtemp(dir='/tmp')); calls=[]
    def acquire(p):calls.append('acquire');p.write_bytes(b'synthetic');p.chmod(0o600)
    def verify(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def observe(p,r):calls.append('observe');assert verify(p)==r['source_sha256']
    return Review(root,lambda:'a'*64 if fixture else None,lambda:private,acquire,verify,observe),calls

def test_happy(tmp_path):
    s,c=make(tmp_path);s.start('yes');assert c==['acquire'];assert b'<video' in s.page();s.decide('approve','yes','Revisão sintética de teste concluída');assert c==['acquire','observe'] and s.state=='COMPLETE' and not s.media.exists()
def test_no_fixture(tmp_path):
    s,c=make(tmp_path,fixture=False)
    with pytest.raises(ValueError):s.start('yes')
    assert c==[]
def test_no_private(tmp_path):
    s,c=make(tmp_path,private=False)
    with pytest.raises(ValueError):s.start('yes')
    assert c==[]
def test_no_approval(tmp_path):
    s,c=make(tmp_path);s.start('yes')
    with pytest.raises(ValueError):s.decide('approve','','Revisão sintética de teste concluída')
    s.decide('reject','','');assert c==['acquire'] and not s.media.exists()
def test_tamper(tmp_path):
    s,c=make(tmp_path);s.start('yes');s.media.write_bytes(b'changed')
    with pytest.raises(ValueError):s.decide('approve','yes','Revisão sintética de teste concluída')
    assert c==['acquire'] and not s.media.exists()
def test_expired(tmp_path):
    s,c=make(tmp_path);s.start('yes');s.deadline=0
    with pytest.raises(ValueError):s.decide('approve','yes','Revisão sintética de teste concluída')
    assert c==['acquire'] and not s.media.exists()
def test_single_transfer(tmp_path):
    s,c=make(tmp_path);s.start('yes')
    with pytest.raises(ValueError):s.start('yes')
    assert c==['acquire'];s.decide('reject','','')

def test_private_gate_exception(tmp_path):
    s,c=make(tmp_path);s.start('yes')
    def unavailable():raise OSError('unavailable')
    s.private_check=unavailable
    with pytest.raises(ValueError):s.check()
    assert s.state=='BLOCKED' and not s.media.exists() and c==['acquire']

def test_unknown_decision(tmp_path):
    s,c=make(tmp_path);s.start('yes')
    with pytest.raises(ValueError):s.decide('unknown','yes','Revisão sintética de teste concluída')
    assert s.state=='REVIEW' and c==['acquire'];s.decide('reject','','')

def test_http_review_range_and_csrf(tmp_path):
    from mobile_review import serve
    import socket, threading, time, http.client, urllib.parse
    s,c=make(tmp_path);s.start('yes')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'https://synthetic-review-{port}.app.github.dev'
    t=threading.Thread(target=serve,args=(s,origin,port));t.start()
    def request(method,path,body=None,headers=None):
        with_connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
        try:
            with_connection.request(method,path,body=body,headers=headers or {});r=with_connection.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally:with_connection.close()
    try:
        for i in range(50):
            try:status,h,b=request('GET','/');break
            except OSError:time.sleep(.02)
        assert status==200 and h['Cache-Control']=='no-store' and b'<video' in b
        status,h,b=request('GET','/media',headers={'Range':'bytes=0-2'});assert status==206 and b==b'syn' and h['Content-Range']=='bytes 0-2/9'
        data=urllib.parse.urlencode({'token':'wrong','decision':'reject'})
        hdr={'Origin':origin,'Content-Type':'application/x-www-form-urlencoded'}
        assert request('POST','/decision',data,hdr)[0]==403
        data=urllib.parse.urlencode({'token':s.token,'decision':'reject'})
        assert request('POST','/decision',data,{**hdr,'Origin':'https://invalid.example'})[0]==403
        assert request('POST','/decision',data,hdr)[0]==303
    finally:
        if s.state=='REVIEW':s.decide('reject','','')
        t.join(4)
    assert not t.is_alive() and s.state=='REJECTED' and c==['acquire']


def test_plan_required(tmp_path):
    s,c=make(tmp_path)
    with pytest.raises(ValueError):s.start('')
    assert s.state=='WAITING' and c==[]
