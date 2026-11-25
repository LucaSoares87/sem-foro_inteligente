import React,{useState} from 'react'
import ledger from '../app/researchEvidence.json'
import {Panel,SectionHeading} from './ui.jsx'
const fmt=v=>Number.isFinite(v)?v.toLocaleString('pt-BR',{maximumFractionDigits:2}):'—'
export default function ResearchEvidence(){
  const [id,setId]=useState('SI-11D')
  const study=ledger.studies.find(s=>s.id===id)
  const download=()=>{
    const url=URL.createObjectURL(new Blob([JSON.stringify(ledger,null,2)],{type:'application/json'}))
    const a=document.createElement('a');a.href=url;a.download='si12-evidencias-sinteticas.json';a.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <Panel>
    <SectionHeading eyebrow="Acervo científico · SI-11" title="Evidências experimentais arquivadas" description="Extrato de médias dos relatórios originais, não telemetria atual. Compare estratégias somente dentro do mesmo protocolo." action={<button className="button-secondary" onClick={download}>Exportar extrato JSON</button>}/>
    <div className="flex flex-wrap gap-2" aria-label="Experimento científico">{ledger.studies.map(s=><button key={s.id} type="button" aria-pressed={id===s.id} onClick={()=>setId(s.id)} className={'button-secondary '+(id===s.id?'border-sky-400 text-sky-200':'')}>{s.id} · {s.label}</button>)}</div>
    <div className="mt-4 grid gap-3 sm:grid-cols-3">
      <div className="info-block"><span>Cenários</span><strong>{fmt(study.cases)}</strong><small>{study.horizon_seconds} s por trajetória</small></div>
      <div className="info-block"><span>Trajetórias</span><strong>{fmt(study.trajectories)}</strong><small>Experimento sintético concluído</small></div>
      <div className="info-block"><span>Gate científico</span><strong className="text-amber-200">{study.research_gate_passed===false?'Não aprovado':'Não definido'}</strong><small>Sem promoção operacional</small></div>
    </div>
    <p className="mt-4 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">{study.note} Nenhuma estimativa representa benefício comprovado em campo.</p>
    <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm" aria-label="Comparação científica arquivada"><thead><tr><th scope="col" className="p-2">Estratégia</th>{study.metrics.map(m=><th key={m.label} scope="col" className="p-2">{m.label}<small className="block text-slate-400">{m.unit}</small></th>)}</tr></thead>
    <tbody>{study.rows.map(row=><tr key={row.name} className="border-t border-slate-800"><th scope="row" className="p-2 font-medium">{row.name}</th>{row.values.map((v,i)=><td key={i} className="p-2 tabular-nums">{fmt(v)}</td>)}</tr>)}</tbody></table></div>
    <details className="mt-4 text-xs text-slate-300"><summary className="cursor-pointer">Proveniência e integridade</summary>
      <p className="mt-2">Relatório SHA-256: <code className="break-all">{study.report_sha256}</code></p><p className="mt-2">ZIP SHA-256: <code className="break-all">{study.zip_sha256}</code></p>
      <a className="mt-2 inline-block underline text-sky-300" href={'https://github.com/LucaSoares87/sem-foro_inteligente/actions/runs/'+study.run} target="_blank" rel="noreferrer">Execução original no GitHub · artefato {study.artifact}</a>
      <p className="mt-2">O artefato do Actions pode expirar; este extrato não substitui o relatório completo.</p>
    </details>
  </Panel>
}
