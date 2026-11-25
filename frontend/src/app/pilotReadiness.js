export const requiredGates=['authorized_model','physical_camera','calibration','field_ground_truth','hardware_benchmark','recovery_drill','human_acceptance']
export function pilotReadiness(data,status){
  if(status!=='current'||!data||data.state!=='available'||data.physical_actuation!==false||data.operational_decision!=='abstain')
    return {state:'unknown',readyCount:null,total:requiredGates.length}
  const gates=Array.isArray(data.gates)?data.gates:[]
  const readyCount=requiredGates.filter(key=>{
    const matches=gates.filter(g=>g.gate===key)
    return matches.length===1&&matches[0].state==='ready'&&Boolean(matches[0].origin)&&matches[0].origin!=='synthetic'&&
      typeof matches[0].artifact_sha256==='string'&&/^[a-f0-9]{64}$/.test(matches[0].artifact_sha256)&&
      Boolean(matches[0].reference)&&Boolean(matches[0].executed_at)
  }).length
  const approved=data.framework_ready===true&&data.pilot_ready===true&&data.pilot_decision==='ready_for_supervised_pilot'&&
    Array.isArray(data.missing_evidence)&&data.missing_evidence.length===0&&readyCount===requiredGates.length
  return {state:approved?'ready':'blocked',readyCount,total:requiredGates.length}
}
export function healthReading(data,status){
  if(status!=='current'||!data) return {label:status==='error'?'Leitura indisponível':'Aguardando leitura',timestamp:null}
  const t=Date.parse(data.timestamp)
  return {label:data.status==='ready'?'Serviços disponíveis':'Serviços degradados',timestamp:Number.isFinite(t)?new Date(t).toISOString():null}
}
export function matchingDecision(source,result){
  return result&&result.source_id===source.source_id&&result.intersection_code===source.intersection_code&&
    Number.isInteger(source.frame_sequence)&&result.frame_sequence===source.frame_sequence&&result.physical_actuation===false&&
    result.operationally_validated===false&&result.operational_decision==='abstain'?result:null
}
