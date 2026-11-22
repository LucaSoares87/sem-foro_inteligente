import React from 'react'
import useHealth from './useHealth.js'
import useRealtime from './useRealtime.js'
import { displayStatus } from './health.js'

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
        <p className="text-sm font-medium uppercase tracking-widest text-sky-300">Fundação técnica / SI-01</p>
        <h1 className="mt-2 text-3xl font-semibold">Semáforos Inteligentes</h1>
        <p className="mt-2 text-slate-400">Centro de inteligência semafórica urbana</p>
      </div>
      <button onClick={refresh} className="rounded-lg border border-slate-600 px-4 py-2 hover:bg-slate-800">Atualizar</button>
    </header>
    <section className="rounded-lg border border-slate-700 p-4">
      <h2 className="font-semibold">Ambiente consultivo</h2>
      <p className="mt-1 text-sm text-slate-300">Nenhuma atuação em semáforos físicos. Detecção e recomendações ainda não implementadas.</p>
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
      <h2 className="font-semibold">Canal de tempo real</h2>
      <p role="status" className="mt-2 text-slate-300">{connections[realtime]}</p>
    </section>
  </main>
}
