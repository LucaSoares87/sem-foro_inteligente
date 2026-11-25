import React,{useState} from 'react'
import ledger from '../app/pimcatEvidence.json'
import {level,colors,fieldLabel,validateLedger} from '../app/pimcatEvidence.js'
import {valueText,downloadJson} from '../app/dailyReport.js'
import {Panel,SectionHeading,EmptyState} from './ui.jsx'
const valid=validateLedger(ledger)
function CriticityHistory(){
  const h=ledger.criticity_history
  const [tick,setTick]=useState(175)
  const snap=h.snapshots.find(s=>s.tick===tick)
  const xy=id=>[40+(h.nodes[id][0]+180)*.98,32+(280-h.nodes[id][1])*.59]
  const counts=Object.fromEntries(Object.keys(colors).map(k=>[k,snap.index.filter(v=>level(v)===k).length]))
  return <section className="mt-5 border-t border-slate-800 pt-4">
    <h3 className="font-semibold text-white">Histórico de criticidade — rede sintética E</h3>
    <p className="text-xs text-slate-400">outage · seed 9100 · global_storage · três snapshots originais; não são dados geográficos nem série diária real.</p>
    <div className="mt-3 flex flex-wrap gap-2">{h.snapshots.map(s=><button type="button" key={s.tick} aria-pressed={s.tick===tick} className="button-secondary" onClick={()=>setTick(s.tick)}>{s.tick} s</button>)}</div>
    <p className="mt-2 text-sm">{snap.central_available?'Central disponível':'Central indisponível — segmentos desconhecidos'}</p>
    <svg viewBox="0 0 640 340" className="mt-3 w-full max-w-3xl rounded-lg bg-slate-950" role="img" aria-label={'Mapa sintético '+tick+' segundos'}>
      {h.edges.map(([id,a,b,cap],i)=>{const [x,y]=xy(a),[u,v]=xy(b),dx=u-x,dy=v-y,len=Math.hypot(dx,dy),ax=x+.66*dx,ay=y+.66*dy;return <g key={id}>
        <line x1={x} y1={y} x2={u} y2={v} stroke={colors[level(snap.index[i])]} strokeWidth="8" strokeLinecap="round"/>
        <polygon points={[[ax,ay],[ax-9*dx/len-4*dy/len,ay-9*dy/len+4*dx/len],[ax-9*dx/len+4*dy/len,ay-9*dy/len-4*dx/len]].map(p=>p.join(',')).join(' ')} fill="#e2e8f0"/>
        <title>{id} · índice {valueText(snap.index[i])} · capacidade proxy {cap}</title></g>})}
      {Object.keys(h.nodes).map(id=>{const [x,y]=xy(id);return <g key={id}><circle cx={x} cy={y} r="5" fill="#f8fafc"/><text x={x+7} y={y-8} fontSize="10" fill="#cbd5e1">{id==='M'?'M RP-07':id}</text></g>})}
    </svg>
    <div className="mt-2 flex flex-wrap gap-3 text-xs">{Object.entries({free:'Livre',moderate:'Moderado',intense:'Intenso',critical:'Crítico',unknown:'Desconhecido'}).map(([k,label])=><span key={k}><i className="mr-1 inline-block h-2 w-2 rounded" style={{background:colors[k]}}/>{label}: {counts[k]}</span>)}</div>
  </section>
}
export default function PimcatEvidence({compact=false}){
  const [id,setId]=useState('PIMCAT E')
  if(!valid)return <Panel><EmptyState title="Acervo científico indisponível" description="Contrato inválido; nenhuma evidência exibida."/></Panel>
  const s=ledger.studies.find(x=>x.id===id)
  return <Panel>
    <SectionHeading eyebrow="PIMCAT F · Acervo separado da operação" title="Inteligência contínua — evidências" description="Extratos verificados de nove relatórios. Comparação somente dentro do mesmo protocolo. Nenhuma promoção ou aprovação de campo." action={<button type="button" className="button-secondary" onClick={()=>downloadJson(ledger,'pimcat-f-evidencias.json')}>Exportar acervo PIMCAT</button>}/>
    <div className="flex flex-wrap gap-2">
      {ledger.studies.map(st=><button type="button" className="button-secondary" aria-pressed={st.id===id} key={st.id} onClick={()=>setId(st.id)}>{st.id}</button>)}
    </div>
    <p className="mt-3 text-sm text-amber-200">{s.origin==='synthetic'?'Simulação arquivada — não telemetria atual':'Replay real externo — saídas do modelo, não referência independente'} · {s.research_gate_passed===false?'Gate científico reprovado':s.key==='c3'?'Precisão independente bloqueada':'Gate binário não definido'}</p>
    <p className="mt-2 text-sm text-slate-300">{s.note}</p>
    <p className="mt-2 text-xs text-slate-400">{s.cases===null?'Mesmo trecho de 8 s, 240 inferências nativas':s.cases+' casos pareados · '+s.trajectories+' trajetórias · '+s.horizon_seconds+' s'}; médias por caso salvo totais explicitados. Ocupação hipotética 1,5 pessoa/veículo nos estudos multimodais.</p>
    <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[540px] text-sm" aria-label="Indicadores comparativos PIMCAT"><thead><tr><th className="p-2 text-left">Estratégia / FPS</th>{s.fields.map(f=><th key={f} className="p-2 text-left">{fieldLabel[f]}</th>)}</tr></thead>
    <tbody>{s.rows.map(row=><tr key={row[0]} className="border-t border-slate-800"><th scope="row" className="p-2 text-left">{row[0]}</th>{row.slice(1).map((v,i)=><td className="p-2 tabular-nums" key={i}>{valueText(v)}</td>)}</tr>)}</tbody></table></div>
    <details className="mt-3 text-xs text-slate-300"><summary>Gates e proveniência</summary>
      {Object.entries(s.gates).map(([k,v])=><p key={k}>{k}: {v?'aprovado':'reprovado'}</p>)}
      <p className="break-all">Relatório SHA-256: {s.report_sha256}</p><p className="break-all">ZIP SHA-256: {s.zip_sha256}</p>
      <a className="text-sky-300 underline" href={'https://github.com/LucaSoares87/sem-foro_inteligente/actions/runs/'+s.run} target="_blank" rel="noreferrer">Execução original · artefato {s.artifact}</a>
      <p>Extrato selecionado; relatório original contém métricas, censura e gates completos. Artefatos Actions podem expirar.</p>
    </details>
    {compact?<p className="mt-4 text-xs text-slate-400"><a className="text-sky-300 underline" href="/laboratorio">Abrir histórico sintético e propostas no laboratório</a>. Nenhum indicador se refere ao cruzamento atual.</p>:<>
      <CriticityHistory/>
      <section className="mt-5 border-t border-slate-800 pt-4"><h3 className="font-semibold text-white">Retroalimentação auditável — propostas não aplicadas</h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">{ledger.suggestions.map(x=><article className="rounded-lg border border-slate-800 p-3" key={x.id}>
        <p className="text-xs text-sky-300">{x.id} · v{x.version} · {x.study}</p><p className="mt-1 text-sm">{x.proposal}</p><p className="mt-2 text-xs text-slate-400">Critério: {x.acceptance}</p>
        <p className="mt-2 break-all text-xs text-slate-400">Fonte: {x.report_sha256}</p><p className="mt-2 text-xs text-amber-200">Não aprovada · não aplicada · sem alteração de restrições</p></article>)}</div></section>
    </>}
  </Panel>
}
