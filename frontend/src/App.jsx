import React from 'react'
import useHealth from './useHealth.js'
import useRealtime from './useRealtime.js'
import { displayStatus } from './health.js'
import ForecastPanel from './ForecastPanel.jsx'
import DecisionPanel from './DecisionPanel.jsx'

const components = [
  ['Backend', 'backend'], ['Banco de dados', 'database'], ['Schema', 'schema'],
  ['WebSocket', 'websocket'], ['Stream de vídeo', 'stream_manager'],
  ['Motor de inferência', 'inference_engine']
]
const connections = { connecting: 'Conectando', connected: 'Conectado', disconnected: 'Reconectando' }

export default function App() {
  const { data, status, refresh } = useHealth()
  const realtime = useRealtime()
  return <main className="mx-auto max-w-6xl space-y-8 px-5 py-10">
    <header className="flex flex-wrap items-start justify-between gap-5 border-b border-slate-700 pb-6">
      <div>
        <p className="text-sm font-medium uppercase tracking-widest text-sky-300">Plataforma técnica / SI-06</p>
        <h1 className="mt-2 text-3xl font-semibold">Semáforos Inteligentes</h1>
        <p className="mt-2 text-slate-400">Centro de inteligência semafórica urbana</p>
      </div>
      <button onClick={refresh} className="rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800">Atualizar</button>
    </header>
    <section className="rounded-lg border border-slate-700 p-4">
      <h2 className="font-semibold">Ambiente consultivo</h2>
      <p className="mt-1 text-sm text-slate-300">Nenhuma atuação em semáforos físicos. Detecção local experimental, sem recomendações operacionais.</p>
    </section>
    <section aria-live="polite">
      <h2 className="mb-4 text-xl font-semibold">Saúde da plataforma</h2>
      <p className="mb-4 text-sm text-slate-400">{status === 'loading' ? 'Consultando...' : status === 'error' ? 'API indisponível. Nova tentativa automática.' : displayStatus(data?.status)}</p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {components.map(([title, key]) => <article key={key} className="rounded-xl border border-slate-700 bg-slate-900 p-5">
          <h3 className="text-sm text-slate-400">{title}</h3>
          <p className="mt-2 text-xl font-medium">{data ? displayStatus(data[key]) : 'Sem dados atuais'}</p>
        </article>)}
      </div>
      <p className="mt-4 text-xs text-slate-400">{data?.timestamp ? 'Última leitura: ' + new Date(data.timestamp).toLocaleString('pt-BR') : ''}</p>
    </section>
    <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="font-semibold">Fontes de vídeo</h2>
      <p className="mt-2 text-sm text-slate-400">Captura e métricas do decodificador; nenhuma contagem de veículos inferida.</p>
      {!data?.video?.sources?.length ? <p className="mt-3 text-sm text-slate-300">Nenhuma fonte disponível na leitura atual.</p> :
        <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="text-slate-400"><tr>{['Fonte','Cruzamento','Estado','Quadros','FPS medido','Latência local'].map(h=><th key={h} scope="col" className="p-2">{h}</th>)}</tr></thead>
          <tbody>{data.video.sources.map(s=><tr key={s.source_id} className="border-t border-slate-700">
            <td className="p-2">{s.source_id}</td><td className="p-2">{s.intersection_code}</td>
            <td className="p-2">{displayStatus(s.state)}</td><td className="p-2">{s.frames_received}</td>
            <td className="p-2">{s.measured_fps==null?'—':s.measured_fps.toFixed(1)}</td>
            <td className="p-2">{s.decode_to_receive_ms==null?'—':s.decode_to_receive_ms.toFixed(1)+' ms'}</td>
          </tr>)}</tbody>
        </table></div>}
    </section>
    <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="font-semibold">Inteligência visual</h2>
      <p className="mt-2 text-sm text-slate-400">Detecções por quadro; não são contagens de passagem, nem medidas homologadas de tráfego.</p>
      <p className="mt-3 text-sm">{data?.vision ? displayStatus(data.vision.state) : 'Sem dados atuais'} · {data?.vision?.purpose === 'validation_only' ? 'Modelo de validação' : data?.vision?.purpose === 'authorized_candidate' ? 'Modelo candidato, não homologado' : 'Sem modelo configurado'}</p>
      {data?.vision?.sources?.map(s => <article key={s.source_id} className="mt-3 rounded border border-slate-700 p-3">
        <h3 className="font-medium">{s.source_id} / {s.intersection_code}</h3>
        <p className="mt-1 text-sm text-slate-300">{s.live ? 'Quadro recente' : 'Último quadro analisado de arquivo encerrado'} · {s.detections_per_frame} detecções · {s.inference_ms.toFixed(1)} ms</p>
        <p className="mt-1 text-xs text-slate-400">{Object.entries(s.classes).map(([k,v]) => k + ': ' + v).join(' · ') || 'Nenhuma detecção no quadro'}</p>
      </article>)}
    </section>
    <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="font-semibold">Rastreamento de veículos</h2>
      <p className="mt-2 text-sm text-slate-400">Associação temporal experimental, por câmera. Veículos visíveis não equivalem a passagens ou fluxo acumulado.</p>
      <p className="mt-3 text-sm">{data?.tracking ? displayStatus(data.tracking.state) : 'Sem dados atuais'}</p>
      {data?.tracking?.sources?.map(s => <article key={s.source_id} className="mt-3 rounded border border-slate-700 p-3">
        <h3 className="font-medium">{s.source_id} / {s.intersection_code}</h3>
        <p className="mt-1 text-sm text-slate-300">{s.live ? 'Quadro recente' : 'Último quadro histórico'} · {s.confirmed_visible} confirmados visíveis · {s.tentative_visible} em confirmação</p>
        <p className="mt-1 text-xs text-slate-400">{s.tracking_ms.toFixed(1)} ms de associação · {s.skipped_frames} quadros não analisados entre observações</p>
      </article>)}
    </section>
    <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="font-semibold">Indicadores experimentais de trânsito</h2>
      <p className="mt-2 text-sm text-slate-400">Cobertura de caixas na imagem, não ocupação física da pista. Passagens observadas por linha e janela, sem extrapolação.</p>
      <p className="mt-3 text-sm">{data?.analytics ? displayStatus(data.analytics.state) : 'Sem dados atuais'}</p>
      {!data?.analytics?.sources?.length && <p className="mt-2 text-sm text-slate-400">Sem medições disponíveis. Verifique fonte, modelo e geometria.</p>}
      {data?.analytics?.sources?.map(s => <article key={s.source_id} className="mt-3 rounded border border-slate-700 p-3">
        <h3 className="font-medium">{s.source_id} / {s.intersection_code}</h3>
        <p className="mt-1 text-xs text-slate-400">{s.live ? 'Quadro recente' : 'Histórico do arquivo'} · {s.purpose==='validation_only'?'Modelo de validação':'Modelo candidato'} · {{initializing:'Inicializando',limited_sampling:'Amostragem limitada',experimental:'Experimental'}[s.quality]} · início {new Date(s.window_started_at).toLocaleString('pt-BR')}</p>
        <p className="mt-1 text-xs text-slate-400">{s.observed_batches} lotes observados · {s.skipped_frames} quadros não analisados · {s.discontinuities} descontinuidades</p>
        {s.regions.map(r=><p key={r.region_id} className="mt-2 text-sm">{r.region_id}: {r.confirmed_visible} veículos confirmados visíveis · {r.image_coverage_pct.toFixed(1)}% cobertura visual</p>)}
        {s.lines.map(l=><p key={l.line_id} className="mt-2 text-sm">{l.line_id}: {l.negative_to_positive} passagens (− → +) · {l.positive_to_negative} (+ → −)</p>)}
      </article>)}
    </section>
    <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="font-semibold">Histórico e previsão de passagens</h2>
      <p className="mt-2 text-sm text-slate-400">Janelas observadas de aproximadamente um minuto. Previsão experimental não equivale à demanda total nem a uma recomendação semafórica.</p>
      {data?.predictive ? <p className="mt-3 text-sm">{data.predictive.state === 'disabled' ? 'Histórico desativado' : displayStatus(data.predictive.state)} · {data.predictive.saved} janelas persistidas nesta execução · {data.predictive.queued} pendentes · {data.predictive.failed} falhas · {data.predictive.dropped} descartes</p> : <p className="mt-3 text-sm">Sem dados atuais</p>}
      <p className="mt-2 text-xs text-slate-400">Fila física, tempo de espera e congestionamento físico: indisponíveis sem calibração.</p>
      {data?.predictive?.state !== 'disabled' && data?.analytics?.sources?.filter(s=>s.live && s.lines.length).map(s=><ForecastPanel key={s.source_id+':'+s.analytics_epoch} source={s}/>)}
    </section>
    <DecisionPanel availability={data?.decision} sources={data?.analytics?.sources || []}/>
    <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="font-semibold">Canal de tempo real</h2>
      <p role="status" className="mt-2 text-slate-300">{connections[realtime]}</p>
    </section>
  </main>
}
