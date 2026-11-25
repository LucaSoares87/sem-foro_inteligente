export const dailyDate=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
export async function fetchDaily(intersection,day,signal,fetcher=fetch){
  if(!/^[A-Z0-9_-]{2,80}$/.test(intersection||'')||!/^\d{4}-\d{2}-\d{2}$/.test(day||''))throw Error('invalid context')
  const response=await fetcher('/api/v1/reporting/intersections/'+encodeURIComponent(intersection)+'/daily?day='+day,{signal,cache:'no-store'})
  if(response.status!==200)throw Error('report unavailable')
  const d=await response.json()
  if(d?.schema_version!==1||d.intersection_code!==intersection||d.date!==day||d.timezone!=='America/Sao_Paulo'||
    !['available','empty'].includes(d.state)||d.origin!=='observed_analytics_source_origin_unverified'||d.aggregation_across_sources!==false||
    d.operationally_validated!==false||d.physical_actuation!==false||d.operational_decision!=='abstain'||
    d.network_total!==null||d.extrapolated!==false||!Array.isArray(d.series)||!Array.isArray(d.sources)||
    !/^[a-f0-9]{64}$/.test(d.report_sha256))throw Error('invalid report')
  for(const s of d.series){
    if(!Number.isFinite(s.coverage_fraction)||s.coverage_fraction<0||s.coverage_fraction>1)throw Error('invalid coverage')
    for(const q of [s.observed,s.limited]){
      if(!q||!Number.isInteger(q.windows)||q.windows<0||!Number.isFinite(q.seconds)||q.seconds<0||
        (q.windows===0?q.passages!==null:!Number.isInteger(q.passages)||q.passages<0))throw Error('invalid count')
    }
  }
  return d
}
export const valueText=v=>Number.isFinite(v)?v.toLocaleString('pt-BR',{maximumFractionDigits:2}):'—'
export function downloadJson(data,name){
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
