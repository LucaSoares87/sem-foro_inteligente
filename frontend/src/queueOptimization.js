export async function fetchQueueOptimization(signal,fetcher=fetch){
  const [queueResponse,optimizationResponse]=await Promise.all([
    fetcher('/api/v1/queue/status',{signal,cache:'no-store'}),
    fetcher('/api/v1/optimization/status',{signal,cache:'no-store'})
  ])
  if(queueResponse.status!==200||optimizationResponse.status!==200) throw new Error('Falha HTTP')
  const queue=await queueResponse.json()
  const optimization=await optimizationResponse.json()
  if(!queue||!Array.isArray(queue.sources)||queue.physical_speed_available!==false||
     queue.operationally_validated!==false||queue.decision_mode!=='simulation_only'){
    throw new Error('Contrato de fila inválido')
  }
  if(!optimization||!Array.isArray(optimization.sources)||optimization.physical_actuation!==false||
     optimization.operationally_validated!==false||optimization.operational_decision!=='abstain'||
     optimization.engineering_weights_validated!==false){
    throw new Error('Contrato de otimização inválido')
  }
  return {queue,optimization}
}

export function optimizationReason(value){
  const labels={
    minor_first_lower_cost:'Fila menor pode ser esvaziada primeiro com menor custo simulado.',
    major_first_lower_cost:'Fluxo dominante apresenta menor custo simulado quando atendido primeiro.',
    no_material_advantage:'Nenhuma sequência apresentou vantagem material suficiente.',
    insufficient_observation_confidence:'Confiança visual insuficiente; o motor se abstém.',
    requires_two_service_groups:'São necessários exatamente dois grupos de serviço explicitamente configurados.',
    no_net_minor_clearance:'A fila menor não possui capacidade líquida de descarga suficiente.',
    minor_exceeds_dynamic_x:'A fila menor excede o X dinâmico seguro para ser limpa primeiro.'
  }
  return labels[value]||'Resultado experimental não reconhecido.'
}
