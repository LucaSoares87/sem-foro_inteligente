"""Aggregate-only technical summary; never publish reviewer reason, video or per-object data."""
import argparse, hashlib, json, subprocess
from pathlib import Path

def read(p):
    if not p.is_file():return None
    d=json.loads(p.read_text());h=d.pop('report_sha256',None)
    if h!=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest():raise ValueError('evidence digest')
    return d

def summary(root,commit,status):
    f=read(root/'fixture-proof.json');o=read(root/'observation.json');source=read(root/'source-proof.json');session=read(root/'mobile-session.json')
    out=['## FR-PERF-02E-OBS-MOBILE — relatório técnico do Codespace',f'Commit `{commit}`; exit `{status}`. Ambiente Codespace, não GitHub Actions. Nenhuma promoção; NO_ELIGIBLE_CANDIDATE da 02C preservado.']
    for name in ('fixture-proof.json','source-proof.json','review-private.json','observation.json','mobile-session.json'):
        p=root/name
        if p.is_file():out.append(f'`{name}` SHA256 `{hashlib.sha256(p.read_bytes()).hexdigest()}`')
    if f:out.append(f'Fixtures: {f["tests"]} testes, passed={f["passed"]}; IPC 2T plain/profile.')
    if source:out.append(f'Fonte SHA256 `{source["sha256"]}`; {len(source["records"])} entradas congeladas.')
    if session:out.append(f'Estado terminal da sessão: {session["state"]}.')
    if not o:out.append('Observação não executada ou relatório não produzido; não interpretar como aprovação.')
    if o:
        out.append(f'Observação complete={o["complete"]}; medições {sum(len(b["rows"]) for b in o["blocks"])}; decisão {o["decision"]}.')
        for b in o['blocks']:
            if b['complete']:out.append(f'Bloco {b["index"]} {b["backend"]}: detector P95 {b["detector"]["p95"]:.6f}ms; IPC P95 {b["ipc"]["p95"]:.6f}ms; CPU-s/frame {b["cpu_per_frame"]:.6f}.')
        for p in o['pairs']:out.append(f'Par {p["reference_block"]}/{p["candidate_block"]}: nonempty={p["reference_nonempty_segments"]}; detecção={p["detection_parity"]}; exato={p["original_exact_equal"]}; semântico={p["semantic_diagnostic_pass"]}; causas agregadas={json.dumps(p["semantic_reason_counts"],sort_keys=True)}.')
    out.append('Nenhum dado pessoal, vídeo, frame ou motivo privado publicado. Revisão humana declarada não equivale a certificação legal. X_safe/RP07/RP08/SI08B, PENDING_HUMAN, physical_actuation=false, Phase B DEFERRED, FIELD_BLOCKED e 95%/200ms intactos.')
    return '\n'.join(out)+'\n'

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('commit');p.add_argument('status',type=int);a=p.parse_args()
    body=summary(a.root,a.commit,a.status);print(body,flush=True)
    subprocess.run(['gh','issue','comment','46','--repo','LucaSoares87/sem-foro_inteligente','--body',body],check=True,timeout=30)
if __name__=='__main__':main()
