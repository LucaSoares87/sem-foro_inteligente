const knownStatuses = {
  online: 'Online', offline: 'Indisponível', current: 'Atualizado',
  outdated: 'Desatualizado', unverified: 'Não verificado',
  available: 'Disponível', not_implemented: 'Não implementado',
  not_loaded: 'Não carregado', ready: 'Pronto', degraded: 'Degradado',
  not_configured: 'Não configurado', idle: 'Inativo', starting: 'Iniciando', loading: 'Carregando modelo', running: 'Recebendo vídeo',
  reconnecting: 'Reconectando', ended: 'Finalizado', stopped: 'Parado', error: 'Falha'
}

export function displayStatus(value) {
  return Object.hasOwn(knownStatuses, value) ? knownStatuses[value] : 'Desconhecido'
}

export async function fetchHealth(signal, fetcher = fetch) {
  const response = await fetcher('/api/v1/health', { signal, cache: 'no-store' })
  if (![200, 503].includes(response.status)) throw new Error('Falha HTTP')
  const data = await response.json()
  if (!data || !['ready', 'degraded'].includes(data.status)) throw new Error('Contrato inválido')
  if ((response.status === 200) !== (data.status === 'ready')) throw new Error('Estado inconsistente')
  return data
}

export function websocketUrl(location) {
  return (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/api/v1/ws/realtime'
}
