import React,{useEffect,useState} from 'react'
import {Panel,SectionHeading,EmptyState} from './ui.jsx'
import {dailyDate,fetchDaily,valueText,downloadJson} from '../app/dailyReport.js'
export default function DailyIntelligence({intersection,intersections=[],enabled=true}){
  const [choice,setChoice]=useState(''),[day,setDay]=useState(dailyDate),[state,setState]=useState({key:'',status:'idle',data:null})
  const code=intersection|| (intersections.some(x=>x.code===choice)?choice:intersections[0]?.code)
  const key=code+':'+day
  const [revision,setRevision]=useState(0)
  useEffect(()=>{
    if(!enabled||!code||!day)return
    let disposed=false;const c=new AbortController(),timer=setTimeout(()=>c.abort(),15000)
    setState({key,status:'loading',data:null})
    fetchDaily(code,day,c.signal).then(data=>{if(!disposed)setState({key,status:'current',data})})
      .catch(()=>{if(!disposed)setState({key,status:'error',data:null})}).finally(()=>clearTimeout(timer))
    return ()=>{disposed=true;clearTimeout(timer);c.abort()}
  },[code,day,enabled,revision])
  const d=enabled&&state.key===key&&state.status==='current'?state.data:null
  return <Panel>
    <SectionHeading eyebrow="PIMCAT F · Observações" title="Relatório diário multimodal" description="Dia civil de São Paulo. Janelas analíticas persistidas, inclusive replay; sem comprovação da origem física histórica. Não soma câmeras, não extrapola lacunas."/>
    <div className="flex flex-wrap gap-3 items-end">
      {!intersection&&intersections.length>0&&<label className="field-label">Cruzamento<select className="field-control" value={code||''} onChange={e=>setChoice(e.target.value)}>{intersections.map(x=><option key={x.code} value={x.code}>{x.code}</option>)}</select></label>}
      <label className="field-label">Data do relatório<input type="date" className="field-control" value={day} max={dailyDate()} onChange={e=>setDay(e.target.value)}/></label>
      <button type="button" className="button-secondary" disabled={!enabled||!code||!day} onClick={()=>setRevision(v=>v+1)}>Atualizar relatório</button>
      {d&&<button type="button" className="button-secondary" onClick={()=>downloadJson(d,'pimcat-diario-'+code+'-'+day+'.json')}>Exportar relatório diário</button>}
    </div>
    {!enabled?<EmptyState title="Histórico desativado" description="Relatório não disponível."/>:!code?<EmptyState title="Sem cruzamento para relatório" description="Selecione um contexto cadastrado; nenhum dado foi inventado."/>:
      !d?<p className="mt-4 text-sm text-slate-400">{state.key===key&&state.status==='error'?'Relatório indisponível ou limite de consulta atingido. Nenhum total parcial exibido.':'Consultando relatório...'}</p>:
      <div className="mt-4 space-y-3">
        <p className="text-sm text-slate-300">{d.complete_windows} janelas completas · {d.boundary_windows_excluded} janelas de fronteira excluídas. Cobertura não é disponibilidade de câmera.</p>
        {d.state==='empty'?<EmptyState title="Sem janelas no dia" description="Passagens desconhecidas, não zero."/>:
          <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-sm" aria-label="Séries diárias por fonte"><thead><tr>{['Fonte / linha / direção / época','Passagens observadas','Passagens limitadas','Cobertura','Não observado (s)'].map(h=><th className="p-2 text-left" key={h}>{h}</th>)}</tr></thead><tbody>
          {d.series.map(s=><tr className="border-t border-slate-800" key={[s.source_id,s.line_id,s.direction,s.analytics_epoch,s.geometry_sha256,s.model_sha256,s.purpose].join(':')}>
            <td className="p-2">{s.source_id} / {s.line_id} / {s.direction}<small className="block break-all text-slate-400">{s.analytics_epoch} · {s.purpose}</small><small className="block">Geometria {s.geometry_sha256.slice(0,8)} · modelo {s.model_sha256.slice(0,8)}</small></td>
            <td className="p-2">{valueText(s.observed.passages)}<small className="block">{s.observed.windows} janelas</small></td><td className="p-2">{valueText(s.limited.passages)}<small className="block">{s.limited.windows} janelas</small></td>
            <td className="p-2">{valueText(s.coverage_fraction*100)}%</td><td className="p-2">{valueText(s.unobserved_seconds)}</td></tr>)}</tbody></table></div>}
        <p className="text-sm text-amber-200">Pedestres, velocidade física, viagem, espera, criticidade de rede e ganhos reais: indisponíveis até evidência apropriada. C3 precisão independente bloqueada.</p>
        <details className="text-xs"><summary>Proveniência do relatório</summary><p className="break-all">SHA-256: {d.report_sha256}</p><p>{d.interval_start} até {d.interval_end} · {d.scope} · abstenção operacional.</p></details>
      </div>}
  </Panel>
}
