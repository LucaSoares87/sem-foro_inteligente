export async function fetchValidation(signal,fetcher=fetch){
  const response=await fetcher('/api/v1/validation/status',{signal,cache:'no-store'})
  if(response.status!==200) throw new Error('Falha HTTP de homologação')
  const data=await response.json()
  if(!data||!['available','error'].includes(data.state)||!Array.isArray(data.gates)||
     typeof data.framework_ready!=='boolean'||typeof data.pilot_ready!=='boolean'||
     data.physical_actuation!==false||data.operational_decision!=='abstain'){
    throw new Error('Contrato de homologação inválido')
  }
  return data
}
