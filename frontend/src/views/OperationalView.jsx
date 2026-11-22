import React from 'react'
import ForecastPanel from '../ForecastPanel.jsx'
import { displayStatus } from '../health.js'
import { DataTable, EmptyState, Panel, SectionHeading, StatusPill } from '../components/ui.jsx'

const platform = [
  ['Backend','backend'],['Banco','database'],['Schema','schema'],['WebSocket','websocket'],
  ['Vídeo','stream_manager'],['Inferência','inference_engine']
]

export default function OperationalView({ data, healthStatus }) {
  const video = data?.video?.sources || []
  const vision = new Map((data?.vision?.sources || []).map(item => [item.source_id, item]))
  const tracking = new Map((data?.tracking?.sources || []).map(item => [item.source_id, item]))
  const analytics = new Map((data?.analytics?.sources || []).map(item => [item.source_id, item]))
  const rows = video.map(source => ({
    ...source, vision: vision.get(source.source_id), tracking: tracking.get(source.source_id), analytics: analytics.get(source.source_id)
  }))
  return <div className="space-y-6">
    <section>
      <p className="eyebrow">Painel Operacional</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Monitoramento técnico e qualidade dos dados</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Detalhamento por fonte e motor. Indicadores experimentais permanecem explicitamente separados de métricas homologadas.</p>
    </section>

    <Panel>
      <SectionHeading title="Saúde da plataforma" description={healthStatus === 'error' ? 'A API não respondeu à última leitura.' : data?.timestamp ? 'Última leitura: ' + new Date(data.timestamp).toLocaleString('pt-BR') : 'Sem leitura atual.'} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {platform.map(([label,key]) => <div key={key} className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
          <p className="text-xs text-slate-500">{label}</p><div className="mt-2"><StatusPill value={data?.[key] || 'not_loaded'} /></div>
        </div>)}
      </div>
    </Panel>

    <Panel>
      <SectionHeading eyebrow="Fontes" title="Câmeras e processamento" description="Estado de captura, inferência, rastreamento e analytics por fonte cadastrada." />
      {rows.length ? <DataTable rows={rows} rowKey={row => row.source_id} columns={[
        { key:'source_id', label:'Fonte' },
        { key:'intersection_code', label:'Cruzamento' },
        { key:'state', label:'Captura', render: row => <StatusPill value={row.state} /> },
        { key:'vision', label:'Detecções', render: row => row.vision ? row.vision.detections_per_frame : '—' },
        { key:'tracking', label:'Tracks visíveis', render: row => row.tracking ? row.tracking.confirmed_visible : '—' },
        { key:'analytics', label:'Analytics', render: row => row.analytics ? displayStatus(row.analytics.quality) : '—' }
      ]} /> : <EmptyState title="Nenhuma fonte cadastrada" description="Cadastre fontes autorizadas para que o painel operacional apresente estados reais." />}
    </Panel>

    <div className="grid gap-6 xl:grid-cols-2">
      <Panel>
        <SectionHeading title="Inteligência visual" description="Resumo do modelo e do rastreamento atual." />
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
      <SectionHeading eyebrow="Previsão" title="Passagens observadas" description="Disponível somente para fontes ativas com histórico contínuo suficiente." />
      {data?.predictive?.state !== 'disabled' && data?.analytics?.sources?.filter(source => source.live && source.lines.length).length
        ? <div className="grid gap-4 xl:grid-cols-2">{data.analytics.sources.filter(source => source.live && source.lines.length).map(source => <ForecastPanel key={source.source_id + ':' + source.analytics_epoch} source={source} />)}</div>
        : <EmptyState title="Sem previsão disponível" description="A plataforma se abstém quando não há histórico ou qualidade suficiente." />}
    </Panel>
  </div>
}
