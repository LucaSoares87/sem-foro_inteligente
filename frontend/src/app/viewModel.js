const arrays = value => Array.isArray(value) ? value : []

export function formatMetric(value, suffix = '') {
  return Number.isFinite(value) ? value.toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + suffix : '—'
}

export function executiveMetrics(data) {
  if (!data) return { intersections: null, sources: null, activeSources: null, visibleTracked: null, observedPassages: null, persistedWindows: null }
  const videoSources = arrays(data.video?.sources)
  const analyticsSources = arrays(data.analytics?.sources)
  const trackingSources = arrays(data.tracking?.sources)
  const codes = new Set([
    ...videoSources.map(source => source.intersection_code),
    ...analyticsSources.map(source => source.intersection_code),
    ...trackingSources.map(source => source.intersection_code)
  ].filter(Boolean))
  const hasSourceInventory = Number.isFinite(data.video?.registered)
  const passages = analyticsSources.length
    ? analyticsSources.reduce((total, source) => total + arrays(source.lines).reduce(
        (sum, line) => sum + (Number(line.negative_to_positive) || 0) + (Number(line.positive_to_negative) || 0), 0), 0)
    : null
  const visibleTracked = trackingSources.length
    ? trackingSources.reduce((sum, source) => sum + (Number(source.confirmed_visible) || 0), 0)
    : null

  return {
    intersections: codes.size || (hasSourceInventory && data.video.registered === 0 ? 0 : null),
    sources: Number.isFinite(data.video?.registered) ? data.video.registered : null,
    activeSources: Number.isFinite(data.video?.active) ? data.video.active : null,
    visibleTracked,
    observedPassages: passages,
    persistedWindows: Number.isFinite(data.predictive?.saved) ? data.predictive.saved : null
  }
}

export function intersectionRows(data) {
  const sources = arrays(data?.video?.sources)
  const grouped = new Map()
  for (const source of sources) {
    const row = grouped.get(source.intersection_code) || {
      code: source.intersection_code, sources: 0, liveSources: 0, errorSources: 0,
      confirmedVisible: null, analyticsQuality: null
    }
    row.sources += 1
    if (source.state === 'running') row.liveSources += 1
    if (['error', 'reconnecting'].includes(source.state)) row.errorSources += 1
    grouped.set(source.intersection_code, row)
  }
  for (const tracked of arrays(data?.tracking?.sources)) {
    const row = grouped.get(tracked.intersection_code)
    if (row && Number.isFinite(tracked.confirmed_visible)) {
      row.confirmedVisible = (row.confirmedVisible ?? 0) + tracked.confirmed_visible
    }
  }
  const qualityRank = { experimental: 0, initializing: 1, limited_sampling: 2 }
  for (const measured of arrays(data?.analytics?.sources)) {
    const row = grouped.get(measured.intersection_code)
    if (!row || !measured.quality) continue
    if (row.analyticsQuality == null || (qualityRank[measured.quality] ?? 3) > (qualityRank[row.analyticsQuality] ?? 3)) {
      row.analyticsQuality = measured.quality
    }
  }
  return [...grouped.values()].sort((a, b) => a.code.localeCompare(b.code))
}

export function collectAlerts(data, healthStatus = 'current', realtime = 'connected') {
  const alerts = []
  const add = (severity, title, detail) => alerts.push({ severity, title, detail })
  if (healthStatus === 'error') add('critical', 'API indisponível', 'A leitura de saúde não pôde ser atualizada.')
  if (data?.status === 'degraded') add('warning', 'Plataforma degradada', 'Uma ou mais dependências de readiness não estão prontas.')
  if (realtime !== 'connected') add('warning', 'Canal em tempo real desconectado', 'A interface está tentando restabelecer o WebSocket.')
  for (const source of arrays(data?.video?.sources)) {
    if (source.state === 'error') add('critical', `Fonte ${source.source_id} indisponível`, source.error_code || 'Falha de captura.')
    if (source.state === 'reconnecting') add('warning', `Fonte ${source.source_id} reconectando`, 'A captura está em recuperação limitada.')
  }
  if (data?.vision?.state === 'error') add('critical', 'Inferência visual indisponível', data.vision.error_code || 'Falha do motor de inferência.')
  for (const [source, code] of Object.entries(data?.tracking?.errors || {})) add('warning', `Tracking degradado em ${source}`, code)
  for (const [source, code] of Object.entries(data?.analytics?.errors || {})) add('warning', `Analytics degradado em ${source}`, code)
  if ((data?.predictive?.failed || 0) > 0) add('warning', 'Falhas no histórico preditivo', `${data.predictive.failed} gravação(ões) falharam nesta execução.`)
  if ((data?.predictive?.dropped || 0) > 0) add('warning', 'Janelas preditivas descartadas', `${data.predictive.dropped} janela(s) não foram persistidas.`)
  if (data?.decision?.operational_decision === 'abstain') add('info', 'Decisão operacional em abstenção', 'O laboratório permanece sintético e não gera atuação física.')
  return alerts
}
