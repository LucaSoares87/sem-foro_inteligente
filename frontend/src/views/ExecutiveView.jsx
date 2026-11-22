import React from 'react'
import { collectAlerts, executiveMetrics, formatMetric, intersectionRows } from '../app/viewModel.js'
import { AlertRow, DataTable, EmptyState, MetricCard, Panel, SectionHeading, StatusPill } from '../components/ui.jsx'

const qualityLabel = value => ({ initializing: 'Inicializando', limited_sampling: 'Amostragem limitada', experimental: 'Experimental' }[value] || 'Sem medição')

export default function ExecutiveView({ data, healthStatus, realtime }) {
  const metrics = executiveMetrics(data)
  const rows = intersectionRows(data)
  const alerts = collectAlerts(data, healthStatus, realtime)
  return <div className="space-y-6">
    <section className="hero-band">
      <div>
        <p className="eyebrow">Painel Executivo · Videowall</p>
        <h1 className="mt-2 max-w-4xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">Visão consolidada da inteligência de trânsito</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">Síntese de disponibilidade, cruzamentos observados e indicadores experimentais. Ausência de dado permanece distinta de zero.</p>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <StatusPill value={data?.status || 'loading'} />
        <StatusPill value={data?.analytics?.state || 'not_configured'} label={'Analytics: ' + (data?.analytics?.state === 'available' ? 'disponível' : data?.analytics?.state === 'not_configured' ? 'não configurado' : 'parcial')} />
        <StatusPill value={data?.decision?.state || 'not_loaded'} label="Decisão: simulação / abstenção" />
      </div>
    </section>

    <section aria-label="Indicadores executivos" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
      <MetricCard label="Cruzamentos observados" value={formatMetric(metrics.intersections)} detail="Derivado das fontes registradas; não representa toda a malha urbana." />
      <MetricCard label="Fontes cadastradas" value={formatMetric(metrics.sources)} detail={metrics.activeSources == null ? 'Atividade sem leitura atual.' : formatMetric(metrics.activeSources) + ' ativas agora.'} tone="good" />
      <MetricCard label="Veículos confirmados visíveis" value={formatMetric(metrics.visibleTracked)} detail="Snapshot de tracking; não é volume acumulado." />
      <MetricCard label="Passagens observadas" value={formatMetric(metrics.observedPassages)} detail="Acumulado da sessão analítica atual, quando disponível." />
      <MetricCard label="Janelas persistidas" value={formatMetric(metrics.persistedWindows)} detail="Histórico salvo nesta execução do serviço." />
      <MetricCard label="Alertas atuais" value={formatMetric(alerts.filter(a => a.severity !== 'info').length)} detail="Condições técnicas detectadas pela plataforma." tone={alerts.some(a => a.severity === 'critical') ? 'critical' : alerts.some(a => a.severity === 'warning') ? 'warning' : 'good'} />
    </section>

    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
      <Panel>
        <SectionHeading eyebrow="Cobertura operacional" title="Cruzamentos e fontes" description="Consolidação dos identificadores já existentes. Geolocalização cartográfica será adicionada na SI-07B, sem posições fictícias." />
        {rows.length ? <DataTable rows={rows} rowKey={row => row.code} columns={[
          { key: 'code', label: 'Cruzamento' },
          { key: 'sources', label: 'Fontes' },
          { key: 'liveSources', label: 'Ativas' },
          { key: 'confirmedVisible', label: 'Visíveis', render: row => formatMetric(row.confirmedVisible) },
          { key: 'analyticsQuality', label: 'Qualidade', render: row => qualityLabel(row.analyticsQuality) }
        ]} /> : <EmptyState title="Nenhum cruzamento disponível" description="O painel não cria pontos ou métricas artificiais quando não existem fontes cadastradas." />}
      </Panel>
      <Panel>
        <SectionHeading eyebrow="Atenção operacional" title="Alertas e abstenções" description="Somente estados derivados dos contratos atuais." />
        {alerts.length ? <ul className="space-y-3">{alerts.slice(0, 8).map((alert, index) => <AlertRow key={alert.title + index} alert={alert} />)}</ul> :
          <EmptyState title="Sem alertas técnicos atuais" description="A ausência de alertas não equivale a homologação de campo." />}
      </Panel>
    </div>

    <Panel>
      <SectionHeading eyebrow="Arquitetura de produto" title="Cobertura geográfica" description="A SI-07A reserva o espaço de navegação e síntese, mas não inventa coordenadas. O mapa real entrará somente quando houver cadastro geográfico explícito por cruzamento." />
      <div className="map-placeholder" role="img" aria-label="Espaço reservado para mapa de cruzamentos na próxima etapa">
        <div>
          <p className="text-sm font-medium text-slate-300">Mapa não configurado</p>
          <p className="mt-1 text-xs text-slate-500">SI-07B: cadastro geográfico, múltiplos cruzamentos e visualização espacial.</p>
        </div>
      </div>
    </Panel>
  </div>
}
