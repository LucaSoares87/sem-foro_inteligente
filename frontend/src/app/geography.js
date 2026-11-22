export function operationalRows(registry = [], data) {
  const liveRows = new Map()
  for (const source of data?.video?.sources || []) {
    const row = liveRows.get(source.intersection_code) || {
      sources:0,liveSources:0,errorSources:0,confirmedVisible:null,analyticsQuality:null
    }
    row.sources++
    if(source.state==='running') row.liveSources++
    if(['error','reconnecting'].includes(source.state)) row.errorSources++
    liveRows.set(source.intersection_code,row)
  }
  for(const item of data?.tracking?.sources || []){
    const row=liveRows.get(item.intersection_code)
    if(row && Number.isFinite(item.confirmed_visible)) row.confirmedVisible=(row.confirmedVisible??0)+item.confirmed_visible
  }
  const rank={experimental:0,initializing:1,limited_sampling:2}
  for(const item of data?.analytics?.sources || []){
    const row=liveRows.get(item.intersection_code)
    if(!row||!item.quality) continue
    if(row.analyticsQuality==null||(rank[item.quality]??3)>(rank[row.analyticsQuality]??3)) row.analyticsQuality=item.quality
  }
  const merged=new Map()
  for(const item of registry){
    merged.set(item.code,{...item,registered:true,...(liveRows.get(item.code)||{
      sources:0,liveSources:0,errorSources:0,confirmedVisible:null,analyticsQuality:null
    })})
  }
  for(const [code,live] of liveRows){
    if(!merged.has(code)) merged.set(code,{code,name:code,district:null,latitude:null,longitude:null,
      has_coordinates:false,enabled:true,registered:false,...live})
  }
  return [...merged.values()].sort((a,b)=>a.code.localeCompare(b.code))
}

export function filterIntersections(rows, search='', district=''){
  const term=search.trim().toLocaleLowerCase('pt-BR')
  return rows.filter(row=>{
    const matchesDistrict=!district||row.district===district
    const haystack=[row.code,row.name,row.district].filter(Boolean).join(' ').toLocaleLowerCase('pt-BR')
    return matchesDistrict&&(!term||haystack.includes(term))
  })
}

export function mapPoints(rows){
  return rows.filter(row=>row.has_coordinates&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude))
}

export function mapProjection(rows,width=1000,height=460,padding=54){
  const points=mapPoints(rows)
  if(!points.length) return []
  let minLat=Math.min(...points.map(p=>p.latitude)),maxLat=Math.max(...points.map(p=>p.latitude))
  let minLon=Math.min(...points.map(p=>p.longitude)),maxLon=Math.max(...points.map(p=>p.longitude))
  if(minLat===maxLat){minLat-=.005;maxLat+=.005}
  if(minLon===maxLon){minLon-=.005;maxLon+=.005}
  const spanLat=maxLat-minLat,spanLon=maxLon-minLon
  return points.map(point=>({
    ...point,
    x:padding+(point.longitude-minLon)/spanLon*(width-padding*2),
    y:padding+(maxLat-point.latitude)/spanLat*(height-padding*2)
  }))
}
