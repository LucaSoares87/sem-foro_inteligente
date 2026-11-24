import React,{useEffect,useMemo,useState} from 'react'
import {collectAlerts,executiveMetrics,formatMetric} from '../app/viewModel.js'
import {operationalRows} from '../app/geography.js'
import {nextPresentationStep,presentationSteps,previousPresentationStep} from '../app/presentation.js'
import GeoOverview from '../components/GeoOverview.jsx'
import HistoryPanel from '../components/HistoryPanel.jsx'
import DecisionPanel from '../DecisionPanel.jsx'
import {MetricCard,Panel,StatusPill} from '../components/ui.jsx'

export default function PresentationView({data,healthStatus,realtime,intersections=[],params={},navigate}){
  const [index,setIndex]=useState(0)
  const [playing,setPlaying]=useState(false)
  const rows=useMemo(()=>operationalRows(intersections,data),[intersections,data])
  const selected=(params.intersection&&rows.some(row=>row.code===params.intersection)?params.intersection:rows[0]?.code)||null
  const meta=rows.find(row=>row.code===selected)||null
  const metrics=executiveMetrics(data)
  const alerts=collectAlerts(data,healthStatus,realtime)
  const step=presentationSteps[index]

  useEffect(()=>{
    if(!playing) return
    const timer=setInterval(()=>setIndex(value=>nextPresentationStep(value)),12000)
    return ()=>clearInterval(timer)
  },[playing])

  const body=step.id==='overview'?<div className="grid gap-5 xl:grid-cols-[1.35fr_.65fr]">
    <Panel><GeoOverview rows={rows} onOpen={()=>{}}/></Panel>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
      <MetricCard label="Cruzamentos" value={formatMetric(intersections.length)} detail="Cadastro explícito"/>
      <MetricCard label="Fontes" value={formatMetric(metrics.sources)} detail={formatMetric(metrics.activeSources)+' ativas'}/>
      <MetricCard label="Alertas" value={formatMetric(alerts.filter(a=>a.severity!=='info').length)} detail="Estados técnicos atuais"/>
    </div>
  </div>:step.id==='intersection'?<Panel>
    <p className="eyebrow">Drill-down operacional</p>
    <h2 className="mt-2 text-3xl font-semibold text-white">{meta?meta.code+' — '+meta.name:'Sem cruzamento disponível'}</h2>
    {meta&&<div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <div className="info-block"><span>Distrito</span><strong>{meta.district||'—'}</strong><small>{meta.registered?'Cadastro administrativo':'Sem cadastro'}</small></div>
      <div className="info-block"><span>Fontes</span><strong>{meta.sources}</strong><small>{meta.liveSources} ativas</small></div>
      <div className="info-block"><span>Tracks</span><strong>{meta.confirmedVisible??'—'}</strong><small>Confirmados visíveis</small></div>
      <div className="info-block"><span>Analytics</span><strong>{meta.analyticsQuality||'—'}</strong><small>Qualidade atual</small></div>
      <div className="info-block"><span>Localização</span><strong>{meta.has_coordinates?'WGS84':'—'}</strong><small>{meta.has_coordinates?meta.latitude.toFixed(5)+', '+meta.longitude.toFixed(5):'Não inferida'}</small></div>
    </div>}
  </Panel>:step.id==='history'?<HistoryPanel intersection={selected} enabled={data?.predictive?.state!=='disabled'}/>:step.id==='intelligence'?<Panel>
    <p className="eyebrow">Cadeia de inteligência</p>
    <h2 className="mt-2 text-3xl font-semibold text-white">Do vídeo à análise consultiva</h2>
    <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      {[['Vídeo',data?.stream_manager],['Inferência',data?.vision?.state],['Tracking',data?.tracking?.state],
        ['Analytics',data?.analytics?.state],['Previsão',data?.predictive?.state],['Decisão',data?.decision?.state]].map(([label,value])=>
        <div key={label} className="info-block"><span>{label}</span><strong>{value||'—'}</strong><small>{label==='Decisão'?'Simulação / abstenção':'Contrato atual'}</small></div>)}
    </div>
    <p className="mt-6 text-sm text-slate-400">A plataforma mantém observado, estimado e sintético separados. A decisão operacional continua em abstenção.</p>
  </Panel>:<div>
    <div className="mb-4 rounded-xl border border-amber-400/25 bg-amber-400/10 p-4 text-sm text-amber-200">
      Etapa sintética da demonstração. Não utiliza este fluxo observado para gerar tempos físicos de semáforo.
    </div>
    <DecisionPanel availability={data?.decision} sources={data?.analytics?.sources||[]}/>
  </div>

  return <main className="presentation-shell">
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
      <div><p className="eyebrow">Demonstração guiada · SI-07C</p><h1 className="mt-1 text-2xl font-semibold text-white">{step.label}</h1></div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill value={data?.status||'loading'}/>
        <button className="button-secondary" type="button" onClick={()=>setPlaying(value=>!value)}>{playing?'Pausar':'Iniciar automático'}</button>
        <button className="button-secondary" type="button" onClick={()=>navigate?.('executive')}>Encerrar</button>
      </div>
    </header>
    <nav aria-label="Etapas da demonstração" className="flex gap-2 overflow-x-auto py-4">
      {presentationSteps.map((item,stepIndex)=><button type="button" key={item.id} onClick={()=>{setIndex(stepIndex);setPlaying(false)}}
        className={'presentation-step '+(stepIndex===index?'presentation-step-active':'')}>
        <span>{stepIndex+1}</span>{item.label}{item.kind==='synthetic'&&<small>Sintético</small>}
      </button>)}
    </nav>
    <section className="min-h-0 flex-1 overflow-auto py-2">{body}</section>
    <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-4">
      <p className="text-xs text-slate-500">Passo {index+1} de {presentationSteps.length} · {step.kind==='synthetic'?'conteúdo sintético':'dados observados/estado atual quando disponíveis'}</p>
      <div className="flex gap-2">
        <button className="button-secondary" type="button" onClick={()=>{setIndex(value=>previousPresentationStep(value));setPlaying(false)}}>Anterior</button>
        <button className="button-secondary" type="button" onClick={()=>{setIndex(value=>nextPresentationStep(value));setPlaying(false)}}>Próximo</button>
      </div>
    </footer>
  </main>
}
