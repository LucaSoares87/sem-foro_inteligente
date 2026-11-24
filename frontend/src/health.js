const knownStatuses = {
  online: 'Online', offline: 'Indisponível', current: 'Atualizado',
  outdated: 'Desatualizado', unverified: 'Não verificado',
  available: 'Disponível', not_implemented: 'Não implementado',
  not_loaded: 'Não carregado', ready: 'Pronto', degraded: 'Degradado',
  not_configured: 'Não configurado', idle: 'Inativo', starting: 'Iniciando', loading: 'Carregando modelo', running: 'Recebendo vídeo',
  reconnecting: 'Reconectando', ended: 'Finalizado', stopped: 'Parado', error: 'Falha',
  initializing: 'Inicializando', limited_sampling: 'Amostragem limitada', experimental: 'Experimental',
  simulation_available: 'Simulação disponível', disabled: 'Desativado',
  blocked: 'Bloqueado', not_run: 'Não executado', failed: 'Falhou',
  pending_human: 'Aceite humano pendente',
  ready_for_supervised_pilot: 'Pronto para piloto supervisionado',
  blocked_by_field_evidence: 'Bloqueado por evidência de campo',
  simulation_preference: 'Preferência simulada', abstain: 'Abstenção',
  simulation_only: 'Somente simulação'
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
