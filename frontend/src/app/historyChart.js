export function seriesKey(series){
  return [series.source_id,series.line_id,series.direction].join('|')
}

export function splitHistorySegments(points=[]){
  const segments=[]
  let current=[]
  let previous=null
  for(const point of points){
    const breakBefore=previous && (
      point.analytics_epoch!==previous.analytics_epoch ||
      point.quality==='limited' ||
      previous.quality==='limited'
    )
    if(breakBefore&&current.length){segments.push(current);current=[]}
    current.push(point)
    if(point.quality==='limited'){segments.push(current);current=[]}
    previous=point
  }
  if(current.length) segments.push(current)
  return segments
}

export function historyChartModel(points=[],width=920,height=280,padding=36){
  if(!points.length) return {points:[],segments:[],maxValue:0,start:null,end:null}
  const times=points.map(point=>Date.parse(point.ended_at))
  let minTime=Math.min(...times),maxTime=Math.max(...times)
  if(minTime===maxTime){minTime-=30000;maxTime+=30000}
  const maxValue=Math.max(1,...points.map(point=>point.observed_passages))
  const projected=points.map((point,index)=>({
    ...point,
    x:padding+(times[index]-minTime)/(maxTime-minTime)*(width-padding*2),
    y:height-padding-(point.observed_passages/maxValue)*(height-padding*2)
  }))
  const lookup=new Map(projected.map(point=>[
    point.ended_at+'|'+point.analytics_epoch+'|'+point.observed_passages+'|'+point.quality,point
  ]))
  const segments=splitHistorySegments(points).map(segment=>segment.map(point=>
    lookup.get(point.ended_at+'|'+point.analytics_epoch+'|'+point.observed_passages+'|'+point.quality)
  ).filter(Boolean))
  return {points:projected,segments,maxValue,start:new Date(minTime),end:new Date(maxTime)}
}

export function summarizeHistory(points=[]){
  if(!points.length) return null
  const values=points.map(point=>point.observed_passages)
  return {
    latest:values.at(-1),
    mean:values.reduce((sum,value)=>sum+value,0)/values.length,
    maximum:Math.max(...values),
    limited:points.filter(point=>point.quality==='limited').length
  }
}
