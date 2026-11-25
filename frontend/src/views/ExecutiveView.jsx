import PimcatEvidence from '../components/PimcatEvidence.jsx'
import DailyIntelligence from '../components/DailyIntelligence.jsx'
import PilotStatus from '../components/PilotStatus.jsx'
import React, {useMemo, useState} from 'react'
import { collectAlerts, executiveMetrics, formatMetric } from '../app/viewModel.js'
import { filterIntersections, operationalRows } from '../app/geography.js'
import GeoOverview from '../components/GeoOverview.jsx'
import { AlertRow, DataTable, EmptyState, MetricCard, Panel, SectionHeading, StatusPill } from '../components/ui.jsx'

const qualityLabel = value => ({ initializing: 'Inicializando', limited_sampling: 'Amostragem limitada', experimental: 'Experimental' }[value] || 'Sem medição')

export default function ExecutiveView({ data, healthStatus, realtime, intersections=[], intersectionStatus, navigate }) {
  const metrics = executiveMetrics(data)
  const rows = useMemo(()=>operationalRows(intersections,data),[intersections,data])
  const [search,setSearch]=useState('')
  const [district,setDistrict]=useState('')
  const districts=useMemo(()=>[...new Set(intersections.map(row=>row.district).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR')),[intersections])
  const filtered=useMemo(()=>filterIntersections(rows,search,district),[rows,search,district])
  const alerts = collectAlerts(data, healthStatus, realtime)
  const registered = intersectionStatus==='current' ? intersections.length : null
  return <div className="space-y-6">
    <section className="hero-band">
      <div>
        <p className="eyebrow">Painel Executivo · Videowall</p>
        <h1 className="mt-2 max-w-4xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">Visão consolidada da inteligência de trânsito</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">Síntese de disponibilidade, cruzamentos cadastrados e indicadores experimentais. Ausência de dado permanece distinta de zero.</p>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <StatusPill value={data?.status || 'loading'} />
        <StatusPill value={data?.geography?.state || 'not_configured'} label={'Geografia: '+(data?.geography?.state==='available'?'disponível':data?.geography?.state==='not_configured'?'não configurada':'indisponível')} />
        <StatusPill value={data?.analytics?.state || 'not_configured'} label={'Analytics: ' + (data?.analytics?.state === 'available' ? 'disponível' : data?.analytics?.state === 'not_configured' ? 'não configurado' : 'parcial')} />
        <StatusPill value={data?.decision?.state || 'not_loaded'} label="Decisão: simulação / abstenção" />
      </div>
    </section>

    <PilotStatus data={data} healthStatus={healthStatus} navigate={navigate}/>
    <section aria-label="Indicadores executivos" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
      <MetricCard label="Cruzamentos cadastrados" value={formatMetric(registered)} detail={intersectionStatus==='error'?'Registro geográfico indisponível.':'Fonte: cadastro geográfico explícito.'} />
      <MetricCard label="Fontes cadastradas" value={formatMetric(metrics.sources)} detail={metrics.activeSources == null ? 'Atividade sem leitura atual.' : formatMetric(metrics.activeSources) + ' ativas agora.'} tone="good" />
      <MetricCard label="Veículos confirmados visíveis" value={formatMetric(metrics.visibleTracked)} detail="Snapshot de tracking; não é volume acumulado." />
      <MetricCard label="Passagens observadas" value={formatMetric(metrics.observedPassages)} detail="Acumulado da sessão analítica atual, quando disponível." />
      <MetricCard label="Janelas persistidas" value={formatMetric(metrics.persistedWindows)} detail="Histórico salvo nesta execução do serviço." />
      <MetricCard label="Alertas atuais" value={formatMetric(alerts.filter(a => a.severity !== 'info').length)} detail="Condições técnicas detectadas pela plataforma." tone={alerts.some(a => a.severity === 'critical') ? 'critical' : alerts.some(a => a.severity === 'warning') ? 'warning' : 'good'} />
    </section>

    <DailyIntelligence intersections={intersectionStatus==='current'?intersections:[]} enabled={data?.predictive?.state!=='disabled'}/>
    <PimcatEvidence compact/>
    <Panel>
      <SectionHeading eyebrow="Cobertura geográfica" title="Mapa de cruzamentos cadastrados" description="Posições WGS84 fornecidas pelo cadastro administrativo. O mapa vetorial não usa tiles, geocodificação ou serviço externo." />
      <GeoOverview rows={filtered} onOpen={code=>navigate?.('operations',{intersection:code})}/>
    </Panel>

    <div className="grid gap-6 xl:grid-cols-[1.45fr_0.8fr]">
      <Panel>
        <SectionHeading eyebrow="Rede monitorada" title="Cruzamentos e fontes"
          description="Inclui cruzamentos cadastrados e fontes ativas ainda sem cadastro geográfico, explicitamente identificadas." />
        <div className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px]">
          <label className="field-label">Buscar
            <input value={search} onChange={event=>setSearch(event.target.value)} className="field-control" placeholder="Código, nome ou distrito"/>
          </label>
          <label className="field-label">Distrito
            <select value={district} onChange={event=>setDistrict(event.target.value)} className="field-control">
              <option value="">Todos</option>
              {districts.map(value=><option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
        {filtered.length ? <DataTable rows={filtered} rowKey={row => row.code} columns={[
          { key: 'code', label: 'Código' },
          { key: 'name', label: 'Cruzamento', render: row => <div><p className="font-medium text-slate-200">{row.name}</p><p className="text-xs text-slate-500">{row.registered ? (row.district || 'Distrito não informado') : 'Sem cadastro geográfico'}</p></div> },
          { key: 'sources', label: 'Fontes' },
          { key: 'liveSources', label: 'Ativas' },
          { key: 'confirmedVisible', label: 'Visíveis', render: row => formatMetric(row.confirmedVisible) },
          { key: 'analyticsQuality', label: 'Qualidade', render: row => qualityLabel(row.analyticsQuality) },
          { key: 'action', label: '', render: row => <button type="button" className="button-secondary" onClick={()=>navigate?.('operations',{intersection:row.code})}>Abrir</button> }
        ]} /> : <EmptyState title="Nenhum cruzamento corresponde ao filtro" description="A plataforma não cria pontos ou métricas artificiais." />}
      </Panel>
      <Panel>
        <SectionHeading eyebrow="Atenção operacional" title="Alertas e abstenções" description="Somente estados derivados dos contratos atuais." />
        {intersectionStatus==='error' && <AlertRow alert={{severity:'warning',title:'Registro geográfico indisponível',detail:'A última consulta ao cadastro de cruzamentos falhou; os dados anteriores, quando existentes, foram preservados em tela.'}}/>}
        {alerts.length ? <ul className={(intersectionStatus==='error'?'mt-3 ':'')+'space-y-3'}>{alerts.slice(0, 8).map((alert, index) => <AlertRow key={alert.title + index} alert={alert} />)}</ul> :
          intersectionStatus!=='error' && <EmptyState title="Sem alertas técnicos atuais" description="A ausência de alertas não equivale a homologação de campo." />}
      </Panel>
    </div>
  </div>
}
