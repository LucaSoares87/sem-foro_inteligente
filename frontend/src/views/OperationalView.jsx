import React, {useMemo} from 'react'
import ForecastPanel from '../ForecastPanel.jsx'
import HistoryPanel from '../components/HistoryPanel.jsx'
import { operationalRows } from '../app/geography.js'
import { displayStatus } from '../health.js'
import { DataTable, EmptyState, Panel, SectionHeading, StatusPill } from '../components/ui.jsx'

const platform = [
  ['Backend','backend'],['Banco','database'],['Schema','schema'],['WebSocket','websocket'],
  ['Vídeo','stream_manager'],['Inferência','inference_engine']
]

export default function OperationalView({ data, healthStatus, intersections=[], intersectionStatus, params={}, navigate }) {
  const catalog=useMemo(()=>operationalRows(intersections,data),[intersections,data])
  const requested=params.intersection
  const selected=(requested&&catalog.some(row=>row.code===requested)?requested:catalog[0]?.code)||null
  const meta=catalog.find(row=>row.code===selected)||null
  const video=(data?.video?.sources||[]).filter(source=>!selected||source.intersection_code===selected)
  const vision = new Map((data?.vision?.sources || []).map(item => [item.source_id, item]))
  const tracking = new Map((data?.tracking?.sources || []).map(item => [item.source_id, item]))
  const analytics = new Map((data?.analytics?.sources || []).map(item => [item.source_id, item]))
  const rows = video.map(source => ({
    ...source, vision: vision.get(source.source_id), tracking: tracking.get(source.source_id), analytics: analytics.get(source.source_id)
  }))
  const forecastSources=(data?.analytics?.sources||[]).filter(source=>source.live&&source.lines.length&&(!selected||source.intersection_code===selected))
  return <div className="space-y-6">
    <section className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="eyebrow">Painel Operacional</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Monitoramento por cruzamento</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Drill-down técnico de fontes, inteligência visual, analytics e previsão. Indicadores experimentais permanecem separados de métricas homologadas.</p>
      </div>
      {catalog.length>0 && <label className="field-label min-w-72">Cruzamento
        <select className="field-control" value={selected||''} onChange={event=>navigate?.('operations',{intersection:event.target.value})}>
          {catalog.map(row=><option key={row.code} value={row.code}>{row.code} — {row.name}</option>)}
        </select>
      </label>}
    </section>

    {meta ? <Panel>
      <SectionHeading eyebrow="Contexto selecionado" title={meta.code+' — '+meta.name}
        description={meta.registered?'Cadastro geográfico explícito.':'Fonte operacional sem cadastro geográfico; localização não será inferida.'} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="info-block"><span>Distrito</span><strong>{meta.district||'—'}</strong><small>{meta.registered?'Cadastro administrativo':'Não cadastrado'}</small></div>
        <div className="info-block"><span>Coordenadas</span><strong>{meta.has_coordinates?'WGS84':'—'}</strong><small>{meta.has_coordinates?meta.latitude.toFixed(5)+', '+meta.longitude.toFixed(5):'Sem coordenadas explícitas'}</small></div>
        <div className="info-block"><span>Fontes</span><strong>{meta.sources}</strong><small>{meta.liveSources} ativas agora</small></div>
        <div className="info-block"><span>Tracks visíveis</span><strong>{meta.confirmedVisible??'—'}</strong><small>Snapshot confirmado</small></div>
        <div className="info-block"><span>Qualidade</span><strong>{meta.analyticsQuality?displayStatus(meta.analyticsQuality):'—'}</strong><small>Estado mais conservador entre feeds</small></div>
      </div>
    </Panel> : <EmptyState title="Nenhum cruzamento disponível" description="Cadastre um cruzamento ou fonte autorizada para habilitar o drill-down operacional."/>}

    <Panel>
      <SectionHeading title="Saúde da plataforma" description={healthStatus === 'error' ? 'A API não respondeu à última leitura.' : data?.timestamp ? 'Última leitura: ' + new Date(data.timestamp).toLocaleString('pt-BR') : 'Sem leitura atual.'} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-7">
        {platform.map(([label,key]) => <div key={key} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
          <p className="text-xs text-slate-500">{label}</p><div className="mt-2"><StatusPill value={data?.[key] || 'not_loaded'} /></div>
        </div>)}
        <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
          <p className="text-xs text-slate-500">Geografia</p><div className="mt-2"><StatusPill value={intersectionStatus==='error'?'error':(data?.geography?.state||'not_configured')} /></div>
        </div>
      </div>
    </Panel>

    <Panel>
      <SectionHeading eyebrow="Fontes" title={selected?'Câmeras e processamento — '+selected:'Câmeras e processamento'} description="Estado de captura, inferência, rastreamento e analytics filtrados pelo cruzamento selecionado." />
      {rows.length ? <DataTable rows={rows} rowKey={row => row.source_id} columns={[
        { key:'source_id', label:'Fonte' },
        { key:'state', label:'Captura', render: row => <StatusPill value={row.state} /> },
        { key:'vision', label:'Detecções', render: row => row.vision ? row.vision.detections_per_frame : '—' },
        { key:'tracking', label:'Tracks visíveis', render: row => row.tracking ? row.tracking.confirmed_visible : '—' },
        { key:'analytics', label:'Analytics', render: row => row.analytics ? displayStatus(row.analytics.quality) : '—' },
        { key:'latency', label:'Latência local', render: row => Number.isFinite(row.decode_to_receive_ms)?row.decode_to_receive_ms.toFixed(1)+' ms':'—' }
      ]} /> : <EmptyState title="Nenhuma fonte neste cruzamento" description="O cadastro geográfico pode existir sem câmera associada; o painel não inventa telemetria." />}
    </Panel>

    <HistoryPanel intersection={selected} enabled={data?.predictive?.state !== 'disabled'} />

    <div className="grid gap-6 xl:grid-cols-2">
      <Panel>
        <SectionHeading title="Inteligência visual" description="Resumo global dos motores; os detalhes de fonte acima permanecem filtrados pelo cruzamento." />
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="info-block"><span>Inferência</span><strong>{displayStatus(data?.vision?.state)}</strong><small>{data?.vision?.purpose === 'validation_only' ? 'Modelo de validação' : data?.vision?.purpose === 'authorized_candidate' ? 'Modelo candidato' : 'Sem modelo configurado'}</small></div>
          <div className="info-block"><span>Tracking</span><strong>{displayStatus(data?.tracking?.state)}</strong><small>{data?.tracking?.algorithm || 'Sem algoritmo ativo'}</small></div>
          <div className="info-block"><span>Analytics</span><strong>{displayStatus(data?.analytics?.state)}</strong><small>{data?.analytics?.processed ?? '—'} lotes processados</small></div>
          <div className="info-block"><span>Histórico</span><strong>{data?.predictive?.state === 'disabled' ? 'Desativado' : displayStatus(data?.predictive?.state)}</strong><small>{data?.predictive?.saved ?? '—'} janelas persistidas</small></div>
        </div>
      </Panel>
      <Panel>
        <SectionHeading title="Restrições operacionais" description="Limitações relevantes para uso responsável." />
        <ul className="space-y-3 text-sm leading-6 text-slate-400">
          <li>Detecções e rastreamentos ainda dependem de modelo treinado e validação de campo.</li>
          <li>Cobertura visual não representa ocupação física da via.</li>
          <li>Previsão representa passagens observadas, não demanda latente.</li>
          <li>O motor de decisão permanece em simulação e abstenção operacional.</li>
        </ul>
      </Panel>
    </div>

    <Panel>
      <SectionHeading eyebrow="Previsão" title={selected?'Passagens observadas — '+selected:'Passagens observadas'} description="Disponível somente para fontes ativas com histórico contínuo suficiente." />
      {data?.predictive?.state !== 'disabled' && forecastSources.length
        ? <div className="grid gap-4 xl:grid-cols-2">{forecastSources.map(source => <ForecastPanel key={source.source_id + ':' + source.analytics_epoch} source={source} />)}</div>
        : <EmptyState title="Sem previsão disponível para este cruzamento" description="A plataforma se abstém quando não há histórico ou qualidade suficiente." />}
    </Panel>
  </div>
}
