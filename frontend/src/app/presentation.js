export const presentationSteps=[
  {id:'overview',label:'Visão municipal',kind:'observed'},
  {id:'intersection',label:'Cruzamento',kind:'observed'},
  {id:'history',label:'Histórico',kind:'observed'},
  {id:'intelligence',label:'Inteligência',kind:'observed'},
  {id:'simulation',label:'Simulação',kind:'synthetic'},
  {id:'evidence',label:'Evidências',kind:'synthetic'},
  {id:'readiness',label:'Homologação',kind:'observed'}
]

export function nextPresentationStep(index,length=presentationSteps.length){
  if(!Number.isInteger(index)||index<0||!Number.isInteger(length)||length<1) return 0
  return (index+1)%length
}

export function previousPresentationStep(index,length=presentationSteps.length){
  if(!Number.isInteger(index)||index<0||!Number.isInteger(length)||length<1) return 0
  return (index-1+length)%length
}
