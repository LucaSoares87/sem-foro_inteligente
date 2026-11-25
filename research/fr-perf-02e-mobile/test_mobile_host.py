import pytest
import mobile_host as h

def test_private_port(monkeypatch):
    monkeypatch.setattr(h,'host_identity',lambda:'owner-host')
    good={'sourcePort':8787,'visibility':'private','browseUrl':'https://owner-host-8787.app.github.dev'}
    monkeypatch.setattr(h,'gh_json',lambda *a:[good]);assert h.private_port('owner-host')
    for change in ({'visibility':'public'},{'visibility':'org'},{'browseUrl':'https://bad.example'},{'sourcePort':8788}):
        monkeypatch.setattr(h,'gh_json',lambda *a:[good|change]);assert not h.private_port('owner-host')
    monkeypatch.setattr(h,'gh_json',lambda *a:[good,good]);assert not h.private_port('owner-host')

def test_identity(monkeypatch):
    monkeypatch.setenv('CODESPACES','true');monkeypatch.setenv('CODESPACE_NAME','owner-host')
    row={'name':'owner-host','owner':{'id':h.OWNER},'repository':{'full_name':h.REPO},'state':'Available'}
    monkeypatch.setattr(h,'gh_json',lambda *a:{'id':h.OWNER} if a[-1]=='user' else row);assert h.host_identity()=='owner-host'
    monkeypatch.setattr(h,'gh_json',lambda *a:{'id':0} if a[-1]=='user' else row)
    with pytest.raises(ValueError):h.host_identity()

@pytest.mark.parametrize('n,failed',[(106,0),(107,1),(107,0)])
def test_junit(tmp_path,n,failed):
    p=tmp_path/'j.xml';p.write_text(f'<testsuite tests="{n}" failures="{failed}" errors="0" skipped="0"/>')
    if n<107 or failed:
        with pytest.raises(ValueError):h.junit_count(p)
    else:assert h.junit_count(p)==n
