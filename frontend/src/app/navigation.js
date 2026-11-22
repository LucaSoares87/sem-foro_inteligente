export const routes = [
  { id: 'executive', path: '/executivo', label: 'Painel Executivo', short: 'Executivo', description: 'Síntese para videowall e gestão' },
  { id: 'operations', path: '/operacional', label: 'Painel Operacional', short: 'Operacional', description: 'Saúde, fontes e inteligência visual' },
  { id: 'laboratory', path: '/laboratorio', label: 'Laboratório', short: 'Laboratório', description: 'Simulação sintética e comparação' }
]

const byPath = new Map(routes.map(route => [route.path, route]))
const byId = new Map(routes.map(route => [route.id, route]))

export function normalizePath(pathname = '/') {
  const clean = ('/' + pathname.split('?')[0].split('#')[0].replace(/^\/+/, '')).replace(/\/+$/, '')
  return clean || '/'
}

export function routeFromPath(pathname) {
  const normalized = normalizePath(pathname)
  return normalized === '/' ? byId.get('executive') : (byPath.get(normalized) || byId.get('executive'))
}

export function routeById(id) {
  return byId.get(id) || byId.get('executive')
}

export function isKnownRoute(pathname) {
  const normalized = normalizePath(pathname)
  return normalized === '/' || byPath.has(normalized)
}
