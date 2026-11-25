export function rectangle(a,b){
  const r=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])]
  if(!r.every(x=>Number.isFinite(x)&&x>=0&&x<=1)||(r[2]-r[0])*(r[3]-r[1])<.0001)throw Error('região inválida')
  return r
}
export function buildDraft({source,code,topology,shapes,distance,continuous}){
  if(!/^[A-Za-z0-9_-]{2,80}$/.test(source)||!/^[A-Z0-9_-]{2,80}$/.test(code)||!['intersection','midblock'].includes(topology)||typeof continuous!=='boolean')throw Error('identificação inválida')
  for(const k of ['approach_a','approach_b','waiting_a','waiting_b','crossing']){
    if(!Array.isArray(shapes[k])||shapes[k].length!==4)throw Error('marque '+k)
    if(rectangle(shapes[k].slice(0,2),shapes[k].slice(2,4)).some((v,i)=>v!==shapes[k][i]))throw Error('retângulo inválido')
  }
  const line=shapes.line
  if(!Array.isArray(line)||line.length!==4||!line.every(x=>Number.isFinite(x)&&x>=0&&x<=1)||Math.hypot(line[2]-line[0],line[3]-line[1])<.02)throw Error('linha inválida')
  if(distance!==null&&(!Number.isFinite(distance)||distance<=0||distance>1000))throw Error('distância inválida')
  return {schema_version:1,status:'draft_not_applied',source_registration:{source_id:source,intersection_code:code,kind:'rtsp',continuous,requires_external_locator:true,requires_authorization_ref:true},
    topology,geometry_candidate:{source_id:source,intersection_code:code,regions:['approach_a','approach_b'].map(region_id=>({region_id,xyxy:shapes[region_id]})),lines:[{line_id:'reference',start:line.slice(0,2),end:line.slice(2,4)}],approaches:[]},
    pedestrian_geometry_draft:{waiting:[shapes.waiting_a,shapes.waiting_b],crossing:shapes.crossing},distance_reference_m:distance,
    metric_calibration_validated:false,visibility_calibrated:false,field_authorized:false,physical_actuation:false,operational_decision:'abstain'}
}
