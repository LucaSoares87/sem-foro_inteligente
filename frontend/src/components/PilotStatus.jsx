import React from 'react'
import useValidation from '../useValidation.js'
import {healthReading,pilotReadiness} from '../app/pilotReadiness.js'
export default function PilotStatus({data,healthStatus,navigate,compact=false}){
  const validation=useValidation()
  const readiness=pilotReadiness(validation.data,validation.status)
  const reading=healthReading(data,healthStatus)
  const label={unknown:'Homologação indisponível',blocked:'Piloto não homologado',ready:'Gates de piloto supervisionado registrados'}[readiness.state]
  return <section aria-label="Prontidão do piloto" className={'rounded-xl border border-slate-700 bg-slate-950/70 '+(compact?'p-3':'p-4')}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-xs uppercase tracking-wider text-slate-400">Prontidão · SI-08B</p>
      <p className={'mt-1 font-semibold '+(readiness.state==='ready'?'text-emerald-200':'text-amber-200')}>{label}</p>
      <p className="text-xs text-slate-400">{readiness.readyCount===null?'Gates sem leitura atual':readiness.readyCount+' de '+readiness.total+' gates com evidência pronta'} · Somente consultivo · Sem atuação física</p></div>
      <div className="text-xs text-slate-300"><p>{reading.label}</p><p>{reading.timestamp?'Leitura UTC: '+reading.timestamp:'Sem timestamp confirmado'}</p></div>
      {navigate&&<button className="button-secondary" onClick={()=>navigate('validation')}>Ver homologação</button>}
    </div>
  </section>
}
