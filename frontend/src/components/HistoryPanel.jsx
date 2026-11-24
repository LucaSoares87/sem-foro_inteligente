import React,{useEffect,useMemo,useState} from 'react'
import useIntersectionHistory from '../useIntersectionHistory.js'
import {historyChartModel,seriesKey,summarizeHistory} from '../app/historyChart.js'
import {EmptyState,Panel,SectionHeading} from './ui.jsx'

const directionLabel=value=>value==='negative_to_positive'?'− → +':'+ → −'
const fmt=value=>Number.isFinite(value)?value.toLocaleString('pt-BR',{maximumFractionDigits:1}):'—'

function HistoryChart({series}){
  const model=useMemo(()=>historyChartModel(series?.points||[]),[series])
  if(!model.points.length) return <EmptyState title="Sem pontos históricos" description="Nenhuma janela persistida para a série selecionada."/>
  const start=model.start.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})
  const end=model.end.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})
  return <div className="history-chart">
    <svg viewBox="0 0 920 280" className="h-full min-h-64 w-full" role="img"
      aria-label={'Passagens observadas por janela. Máximo '+model.maxValue+'.'}>
      {[36,105,174,244].map(y=><line key={y} x1="36" x2="884" y1={y} y2={y} className="history-grid"/>)}
      {model.segments.filter(segment=>segment.length>1).map((segment,index)=>
        <polyline key={index} className="history-line" points={segment.map(point=>point.x+','+point.y).join(' ')}/>)}
      {model.points.map((point,index)=><circle key={index} cx={point.x} cy={point.y} r="5"
        className={'history-point '+(point.quality==='limited'?'history-point-limited':'')}>
        <title>{new Date(point.ended_at).toLocaleString('pt-BR')} · {point.observed_passages} passagens · {point.quality==='limited'?'amostragem limitada':'observado'}</title>
      </circle>)}
      <text x="36" y="274" className="fill-slate-500 text-[12px]">{start}</text>
      <text x="884" y="274" textAnchor="end" className="fill-slate-500 text-[12px]">{end}</text>
      <text x="26" y="42" textAnchor="end" className="fill-slate-500 text-[12px]">{model.maxValue}</text>
      <text x="26" y="247" textAnchor="end" className="fill-slate-500 text-[12px]">0</text>
    </svg>
  </div>
}

export default function HistoryPanel({intersection,enabled=true}){
  const {data,status}=useIntersectionHistory(intersection,enabled)
  const [selection,setSelection]=useState('')
  const options=data?.series||[]
  useEffect(()=>{
    if(!options.length){setSelection('');return}
    if(!options.some(series=>seriesKey(series)===selection)) setSelection(seriesKey(options[0]))
  },[data,selection])
  const selected=options.find(series=>seriesKey(series)===selection)||options[0]
  const summary=summarizeHistory(selected?.points||[])
  return <Panel>
    <SectionHeading eyebrow="Histórico observado" title={intersection?'Evolução por fonte e linha — '+intersection:'Evolução por fonte e linha'}
      description="Janelas persistidas de aproximadamente 60 s. Câmeras não são somadas entre si; mudanças de epoch e amostragem limitada interrompem a linha do gráfico."/>
    {!enabled?<EmptyState title="Histórico desativado" description="A persistência não está habilitada neste ambiente."/>:
      !intersection?<EmptyState title="Selecione um cruzamento" description="O histórico é consultado somente no contexto selecionado."/>:
      status==='loading'&&!data?<p className="text-sm text-slate-400">Consultando histórico...</p>:
      status==='error'&&!data?<EmptyState title="Histórico indisponível" description="A última consulta falhou; nenhum valor foi fabricado."/>:
      !options.length?<EmptyState title="Sem histórico para este cruzamento" description="Ainda não existem janelas observadas persistidas para as fontes atuais."/>:
      <>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <label className="field-label min-w-72">Série
            <select className="field-control" value={seriesKey(selected)} onChange={event=>setSelection(event.target.value)}>
              {options.map(series=><option key={seriesKey(series)} value={seriesKey(series)}>
                {series.source_id} · {series.line_id} · {directionLabel(series.direction)}
              </option>)}
            </select>
          </label>
          <div className="grid grid-cols-4 gap-2 text-center text-xs">
            <div className="history-stat"><span>Última</span><strong>{fmt(summary?.latest)}</strong></div>
            <div className="history-stat"><span>Média</span><strong>{fmt(summary?.mean)}</strong></div>
            <div className="history-stat"><span>Máxima</span><strong>{fmt(summary?.maximum)}</strong></div>
            <div className="history-stat"><span>Limitadas</span><strong>{summary?.limited??'—'}</strong></div>
          </div>
        </div>
        <HistoryChart series={selected}/>
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
          <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-sky-300"/>Janela observada</span>
          <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-300"/>Amostragem limitada</span>
          <span>{data.windows} janela(s) carregadas · sem agregação entre câmeras</span>
          {status==='error'&&<span className="text-amber-300">Atualização recente falhou; exibindo último histórico válido.</span>}
        </div>
      </>}
  </Panel>
}
