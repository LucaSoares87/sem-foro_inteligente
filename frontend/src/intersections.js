export async function fetchIntersections(signal, fetcher = fetch) {
  const response = await fetcher('/api/v1/intersections', { signal, cache: 'no-store' })
  if (response.status !== 200) throw new Error('Falha no registro geográfico')
  const data = await response.json()
  if (!Array.isArray(data)) throw new Error('Contrato geográfico inválido')
  for (const row of data) {
    if (!row || typeof row.code !== 'string' || typeof row.name !== 'string' || typeof row.enabled !== 'boolean') {
      throw new Error('Contrato geográfico inválido')
    }
    const pair = row.latitude != null && row.longitude != null
    if (row.has_coordinates !== pair) throw new Error('Coordenadas inconsistentes')
  }
  return data
}
