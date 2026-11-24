import React from 'react'
import { routes, shouldHandleNavigation } from '../app/navigation.js'
import { StatusPill } from './ui.jsx'

const realtimeLabels = { connecting: 'Conectando', connected: 'Tempo real conectado', disconnected: 'Reconectando' }

export default function AppShell({ route, navigate, data, healthStatus, realtime, refresh, children }) {
  const healthValue = healthStatus === 'error' ? 'error' : (data?.status || 'loading')
  return <div className="min-h-screen">
    <a href="#conteudo" className="skip-link">Ir para o conteúdo</a>
    <div className="mx-auto grid min-h-screen max-w-[1800px] lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="hidden border-r border-slate-800/80 bg-slate-950/80 px-5 py-6 lg:flex lg:flex-col">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-300">SI-08B</p>
          <h1 className="mt-2 text-xl font-semibold tracking-tight text-white">Semáforos Inteligentes</h1>
          <p className="mt-2 text-xs leading-5 text-slate-500">Centro de inteligência urbana em modo consultivo.</p>
        </div>
        <nav aria-label="Ambientes da plataforma" className="mt-8 space-y-2">
          {routes.map(item => <a key={item.id} href={item.path}
            aria-current={route.id === item.id ? 'page' : undefined}
            onClick={event => { if (shouldHandleNavigation(event)) { event.preventDefault(); navigate(item.id) } }}
            className={'nav-item ' + (route.id === item.id ? 'nav-item-active' : '')}>
            <span className="text-sm font-medium">{item.label}</span>
            <span className="mt-1 block text-[11px] leading-4 text-slate-500">{item.description}</span>
          </a>)}
        </nav>
        <div className="mt-auto rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-xs font-medium text-slate-300">Modo de operação</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">Consultivo e simulação. Nenhuma atuação em controlador físico.</p>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-[#07101d]/90 px-4 py-3 backdrop-blur-xl sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-sky-300 lg:hidden">Semáforos Inteligentes</p>
              <h2 className="truncate text-lg font-semibold text-white">{route.label}</h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill value={healthValue} label={healthStatus === 'loading' ? 'Consultando' : undefined} />
              <span className={'status-pill ' + (realtime === 'connected' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200' : 'border-amber-400/25 bg-amber-400/10 text-amber-200')}>{realtimeLabels[realtime] || 'Tempo real'}</span>
              <button type="button" onClick={refresh} className="button-secondary">Atualizar</button>
            </div>
          </div>
          <nav aria-label="Ambientes da plataforma no celular" className="mt-3 flex gap-2 overflow-x-auto pb-1 lg:hidden">
            {routes.map(item => <a key={item.id} href={item.path}
              aria-current={route.id === item.id ? 'page' : undefined}
              onClick={event => { if (shouldHandleNavigation(event)) { event.preventDefault(); navigate(item.id) } }}
              className={'mobile-tab ' + (route.id === item.id ? 'mobile-tab-active' : '')}>{item.short}</a>)}
          </nav>
        </header>
        <main id="conteudo" tabIndex="-1" className="px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  </div>
}
