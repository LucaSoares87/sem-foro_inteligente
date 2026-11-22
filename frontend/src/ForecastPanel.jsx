import React, {useEffect, useState} from 'react'

const reasons = {
  insufficient_contiguous_quality_windows: 'Histórico contínuo e confiável insuficiente.',
  no_current_live_snapshot: 'Sem observação atual de fonte ativa.',
  history_not_recent: 'Histórico recente insuficiente.',
  recent_discontinuity: 'Interrupção recente na captura.',
  session_changed: 'Sessão alterada durante a consulta.'
}

export default function ForecastPanel({source}) {
  const [selection,setSelection]=useState(source.lines[0].line_id)
  const [direction,setDirection]=useState('negative_to_positive')
  const [result,setResult]=useState(null)
  const [error,setError]=useState(false)
  const line=source.lines.some(l=>l.line_id===selection)?selection:source.lines[0].line_id
  useEffect(()=>{
    const controller=new AbortController()
    const params=new URLSearchParams({line_id:line,direction})
    setResult(null)
    setError(false)
    async function update(){
      try{
        const res=await fetch('/api/v1/predictive/sources/'+encodeURIComponent(source.source_id)+'/forecast?'+params,{signal:controller.signal,cache:'no-store'})
        if(!res.ok) throw new Error('unavailable')
        const data=await res.json()
        if(!controller.signal.aborted){setResult(data);setError(false)}
      }catch(e){if(!controller.signal.aborted){setError(true);setResult(null)}}
    }
    update()
    const timer=setInterval(update,15000)
    return ()=>{clearInterval(timer);controller.abort()}
  },[source.source_id,line,direction])
  const fmt=n=>Number.isFinite(n)?n.toLocaleString('pt-BR',{maximumFractionDigits:2}):'—'
  return <article className="mt-3 rounded border border-slate-700 p-3">
    <h3 className="font-medium">{source.source_id} / {source.intersection_code}</h3>
    <div className="mt-2 flex flex-wrap gap-3 text-sm">
      <label>Linha <select className="bg-slate-800 rounded p-1" value={line} onChange={e=>{setResult(null);setSelection(e.target.value)}}>{source.lines.map(l=><option key={l.line_id}>{l.line_id}</option>)}</select></label>
      <label>Sentido <select className="bg-slate-800 rounded p-1" value={direction} onChange={e=>{setResult(null);setDirection(e.target.value)}}><option value="negative_to_positive">− → +</option><option value="positive_to_negative">+ → −</option></select></label>
    </div>
    {error ? <p className="mt-2 text-sm text-slate-400">Histórico indisponível.</p> : !result ? <p className="mt-2 text-sm text-slate-400">Consultando...</p> : result.state==='experimental' ? <div className="mt-3 text-sm">
      <p>{fmt(result.estimate)} passagens observadas por minuto (previsão de 60 s).</p>
      <p className="text-slate-400">Faixa empírica de erro: {result.empirical_error_band.map(x=>fmt(x)).join(' a ')} · {result.backtest_samples} pontos de backtest.</p>
      <p className="text-xs text-slate-400">Experimental, não homologado · {result.purpose==='validation_only'?'Modelo de validação':'Modelo candidato'}</p>
    </div> : <p className="mt-2 text-sm text-slate-400">{reasons[result.reason]||'Previsão indisponível.'}</p>}
  </article>
}
