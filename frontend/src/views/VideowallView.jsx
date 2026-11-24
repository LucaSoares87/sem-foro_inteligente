import React,{useMemo} from 'react'
import {collectAlerts,executiveMetrics,formatMetric} from '../app/viewModel.js'
import {operationalRows} from '../app/geography.js'
import GeoOverview from '../components/GeoOverview.jsx'
import {AlertRow,EmptyState,MetricCard,StatusPill} from '../components/ui.jsx'

export default function VideowallView({data,healthStatus,realtime,intersections=[],intersectionStatus,navigate}){
  const metrics=executiveMetrics(data)
  const rows=useMemo(()=>operationalRows(intersections,data),[intersections,data])
  const alerts=collectAlerts(data,healthStatus,realtime)
  const attention=rows.filter(row=>row.errorSources>0||row.liveSources<row.sources)
    .sort((a,b)=>b.errorSources-a.errorSources||a.code.localeCompare(b.code)).slice(0,8)
  const registered=intersectionStatus==='current'?intersections.length:null
  return <main className="videowall-shell">
    <header className="videowall-header">
      <div>
        <p className="eyebrow">Centro de Operações · Videowall</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">Semáforos Inteligentes</h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill value={data?.status||'loading'}/>
        <span className="status-pill border-sky-400/20 bg-sky-400/10 text-sky-200">Consultivo</span>
        <button type="button" className="button-secondary" onClick={()=>navigate?.('executive')}>Sair do videowall</button>
      </div>
    </header>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      <MetricCard label="Cruzamentos" value={formatMetric(registered)} detail="Cadastro geográfico"/>
      <MetricCard label="Fontes" value={formatMetric(metrics.sources)} detail={metrics.activeSources==null?'—':formatMetric(metrics.activeSources)+' ativas'}/>
      <MetricCard label="Tracks visíveis" value={formatMetric(metrics.visibleTracked)} detail="Snapshot confirmado"/>
      <MetricCard label="Passagens" value={formatMetric(metrics.observedPassages)} detail="Sessão analítica atual"/>
      <MetricCard label="Histórico" value={formatMetric(metrics.persistedWindows)} detail="Janelas persistidas"/>
      <MetricCard label="Alertas" value={formatMetric(alerts.filter(a=>a.severity!=='info').length)} detail="Condições técnicas"
        tone={alerts.some(a=>a.severity==='critical')?'critical':alerts.some(a=>a.severity==='warning')?'warning':'good'}/>
    </section>
    <section className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[1.55fr_.75fr]">
      <div className="surface-panel min-h-0 overflow-hidden">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold text-white">Cobertura geográfica</h2>
          <span className="text-xs text-slate-500">WGS84 · sem mapa-base externo</span></div>
        <GeoOverview rows={rows} onOpen={code=>navigate?.('operations',{intersection:code})}/>
      </div>
      <div className="grid min-h-0 gap-4 lg:grid-rows-2 xl:grid-rows-2">
        <section className="surface-panel min-h-0 overflow-auto">
          <h2 className="text-lg font-semibold text-white">Cruzamentos em atenção</h2>
          {attention.length?<ul className="mt-3 space-y-2">{attention.map(row=><li key={row.code} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="flex items-center justify-between gap-2"><strong className="text-sm text-slate-200">{row.code}</strong><span className="text-xs text-slate-500">{row.liveSources}/{row.sources} fontes ativas</span></div>
            <p className="mt-1 text-xs text-slate-500">{row.name}</p>
          </li>)}</ul>:<EmptyState title="Sem cruzamentos em atenção" description="Isso não equivale a homologação operacional."/>}
        </section>
        <section className="surface-panel min-h-0 overflow-auto">
          <h2 className="text-lg font-semibold text-white">Alertas atuais</h2>
          {alerts.length?<ul className="mt-3 space-y-2">{alerts.slice(0,6).map((alert,index)=><AlertRow key={alert.title+index} alert={alert}/>)}</ul>:
            <EmptyState title="Sem alertas técnicos atuais" description="A ausência de alerta não implica ausência de risco de campo."/>}
        </section>
      </div>
    </section>
    <footer className="flex items-center justify-between text-[11px] text-slate-600">
      <span>Dados observados e experimentais identificados pelos respectivos motores.</span>
      <span>Nenhuma atuação física.</span>
    </footer>
  </main>
}
