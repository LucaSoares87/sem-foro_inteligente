export async function fetchIntersectionHistory(intersection, signal, fetcher=fetch, limit=60) {
  if(!/^[A-Z0-9_-]{2,80}$/.test(intersection||'')) throw new Error('Cruzamento inválido')
  const response=await fetcher('/api/v1/predictive/intersections/'+encodeURIComponent(intersection)+'/history?limit='+limit,
    {signal,cache:'no-store'})
  if(response.status===503) throw new Error('Histórico indisponível')
  if(response.status!==200) throw new Error('Falha HTTP')
  const data=await response.json()
  if(!data||data.intersection_code!==intersection||!Array.isArray(data.series)||data.aggregation_across_sources!==false){
    throw new Error('Contrato histórico inválido')
  }
  for(const series of data.series){
    if(!series||typeof series.source_id!=='string'||typeof series.line_id!=='string'||
       !['negative_to_positive','positive_to_negative'].includes(series.direction)||!Array.isArray(series.points)){
      throw new Error('Série histórica inválida')
    }
    for(const point of series.points){
      if(!Number.isFinite(point.observed_passages)||point.observed_passages<0||
         !['observed','limited'].includes(point.quality)||typeof point.analytics_epoch!=='string'||
         Number.isNaN(Date.parse(point.ended_at))){
        throw new Error('Ponto histórico inválido')
      }
    }
  }
  return data
}
