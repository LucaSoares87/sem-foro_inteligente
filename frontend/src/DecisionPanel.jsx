import React, {useEffect,useState} from 'react'

const presets = {balanced:'Demanda equilibrada',asymmetric:'Demanda assimétrica',surge:'Pico temporário',overload:'Sobrecarga',empty:'Sem chegadas'}
const reasons = {lower_queue_area_without_regression:'Menor área de fila, sem piora dos indicadores comparados.',
  adaptive_tradeoff_or_no_gain:'A adaptação não demonstrou ganho sem perdas nos indicadores comparados.',
  equal_outcomes:'As duas políticas tiveram resultados equivalentes.'}
const metrics=[['Chegadas','arrivals'],['Atendimentos','served'],['Fila final','final_queue'],
  ['Pico combinado','peak_combined'],['Área acumulada de fila','queue_area'],['Área de fila A','queue_area_a'],['Área de fila B','queue_area_b']]

export default function DecisionPanel({availability,sources}){
  const [preset,setPreset]=useState('asymmetric')
  const [result,setResult]=useState(null)
  const [error,setError]=useState(false)
  useEffect(()=>{
    const controller=new AbortController()
    setResult(null);setError(false)
    async function load(){
      try{
        const res=await fetch('/api/v1/decision/demo?preset='+encodeURIComponent(preset),{signal:controller.signal,cache:'no-store'})
        if(!res.ok) throw new Error('unavailable')
        const data=await res.json()
        if(data.origin!=='synthetic'||data.physical_actuation!==false||data.operationally_validated!==false) throw new Error('invalid response')
        if(!controller.signal.aborted) setResult(data)
      }catch(e){if(!controller.signal.aborted) setError(true)}
    }
    load()
    return ()=>controller.abort()
  },[preset])
  return <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
    <h2 className="font-semibold">Laboratório de inteligência semafórica</h2>
    <p className="mt-2 text-sm text-amber-300">SIMULAÇÃO SINTÉTICA — sem atuação física. Dois grupos abstratos; unidades de tempo e capacidade não representam parâmetros de vias reais.</p>
    <p className="mt-2 text-sm text-slate-300">Decisão operacional: {availability?.operational_decision==='abstain'?'abstenção — dados não homologados':'indisponível'}. {sources.length>0?'Medições visuais permanecem separadas do laboratório.':''}</p>
    <label className="mt-3 block text-sm">Cenário <select className="ml-2 rounded bg-slate-800 p-2" value={preset} onChange={e=>{setResult(null);setError(false);setPreset(e.target.value)}}>{Object.entries(presets).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
    {error?<p className="mt-3 text-sm">Simulador indisponível.</p>:!result?<p className="mt-3 text-sm">Consultando...</p>:<>
      <p className="mt-3 font-medium">Preferência no modelo: {{fixed:'fixa',adaptive:'adaptativa',equivalent:'equivalentes'}[result.preferred_in_simulation]}</p>
      <p className="mt-1 text-sm text-slate-400">{reasons[result.reason]}</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
        <thead><tr><th scope="col" className="p-2">Indicador simulado</th><th scope="col" className="p-2">Fixa</th><th scope="col" className="p-2">Adaptativa</th></tr></thead>
        <tbody>{metrics.map(([label,key])=><tr key={key} className="border-t border-slate-700"><th scope="row" className="p-2 font-normal">{label}</th><td className="p-2">{result.fixed[key]}</td><td className="p-2">{result.adaptive[key]}</td></tr>)}</tbody>
      </table></div>
      <p className="mt-2 text-sm text-slate-400">Variação da área de fila (redução): {result.queue_area_reduction_pct===null?'não aplicável':result.queue_area_reduction_pct.toFixed(1)+'%'}. Área = soma das filas por unidade simulada, não atraso medido.</p>
      <details className="mt-3 text-sm"><summary className="cursor-pointer">Resultados por ciclo sintético</summary>
        <div className="overflow-x-auto"><table className="mt-2 w-full text-left text-xs">
          <thead><tr>{['Ciclo','Chegadas A/B','Fila final fixa A/B','Fila final adaptativa A/B'].map(x=><th key={x} scope="col" className="p-2">{x}</th>)}</tr></thead>
          <tbody>{result.fixed.cycles.map((c,i)=><tr key={c.cycle} className="border-t border-slate-700"><td className="p-2">{c.cycle}</td><td className="p-2">{c.arrivals_a}/{c.arrivals_b}</td><td className="p-2">{c.end_a}/{c.end_b}</td><td className="p-2">{result.adaptive.cycles[i].end_a}/{result.adaptive.cycles[i].end_b}</td></tr>)}</tbody>
        </table></div>
      </details>
      <p className="mt-3 break-all text-xs text-slate-400">Identificação reprodutível do resultado: {result.result_sha256}</p>
    </>}
  </section>
}
