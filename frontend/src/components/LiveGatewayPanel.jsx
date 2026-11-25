import React,{useEffect,useState} from 'react'
import {Panel,SectionHeading} from './ui.jsx'
import {rectangle,buildDraft} from '../app/cameraDraft.js'
import {downloadJson,valueText} from '../app/dailyReport.js'
const kinds={approach_a:'Aproximação A',approach_b:'Aproximação B',waiting_a:'Espera A',waiting_b:'Espera B',crossing:'Faixa de pedestres',line:'Linha de referência'}
export default function LiveGatewayPanel({gateway}){
  const [source,setSource]=useState(''),[code,setCode]=useState(''),[topology,setTopology]=useState('intersection'),[continuous,setContinuous]=useState(false)
  const [kind,setKind]=useState('approach_a'),[first,setFirst]=useState(null),[shapes,setShapes]=useState({}),[distance,setDistance]=useState(''),[image,setImage]=useState(null),[error,setError]=useState('')
  useEffect(()=>()=>{if(image)URL.revokeObjectURL(image)},[image])
  const mark=e=>{
    const r=e.currentTarget.getBoundingClientRect(),p=[Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]
    if(!first){setFirst(p);return}
    try{const v=kind==='line'?[...first,...p]:rectangle(first,p);setShapes(s=>({...s,[kind]:v}));setError('')}catch{setError('Marcação inválida; selecione dois pontos distintos.')}setFirst(null)
  }
  const exportDraft=()=>{try{downloadJson(buildDraft({source,code,topology,shapes,distance:distance===''?null:Number(distance),continuous}),'camera-calibracao-rascunho.json');setError('')}catch(e){setError(e.message)}}
  return <Panel><SectionHeading eyebrow="PIMCAT H1 · Gateway" title="Recepção contínua e calibração" description="Telemetria de captura, não disponibilidade de campo ou inferência. Sem endereço de câmera ou segredo na interface. Supervisão opt-in via registro externo."/>
    {gateway?.sources?.length?<div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{['Fonte','Desejado','Captura','Observação','Idade (s)','Frames no processo','Reinícios'].map(h=><th key={h} className="p-2 text-left">{h}</th>)}</tr></thead><tbody>{gateway.sources.map(s=><tr key={s.source_id}><td className="p-2">{s.source_id}</td><td>{s.desired?'Sim':'Não'}</td><td>{s.capture_state}</td><td>{s.observation==='recent_frames'?'Frames recentes':'Desconhecida'}</td><td>{valueText(s.last_frame_age_seconds)}</td><td>{valueText(s.process_observed_frames)}</td><td>{valueText(s.supervisor_restarts)}</td></tr>)}</tbody></table></div>:<p className="text-sm text-slate-400">Sem fontes disponíveis no contexto de saúde. Nenhuma câmera conectada presumida.</p>}
    <details className="mt-4"><summary className="cursor-pointer font-semibold">Assistente visual — rascunho de câmera</summary>
      <p className="my-3 text-sm text-amber-200">Desenho sintético ou imagem de referência previamente sanitizada e autorizada, mantida somente no navegador. Marque dois pontos por região. Não aprova geometria, escala, visibilidade ou campo; nenhuma configuração aplicada.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="field-label">Identificador da câmera<input className="field-control" value={source} onChange={e=>setSource(e.target.value)}/></label>
        <label className="field-label">Cruzamento<input className="field-control" value={code} onChange={e=>setCode(e.target.value)}/></label>
        <label className="field-label">Topologia<select className="field-control" value={topology} onChange={e=>setTopology(e.target.value)}><option value="intersection">Cruzamento</option><option value="midblock">RP-07 faixa isolada</option></select></label>
        <label className="field-label">Distância de referência medida (m, opcional)<input type="number" min="0.01" max="1000" className="field-control" value={distance} onChange={e=>setDistance(e.target.value)}/></label>
        <label className="field-label">Imagem local sanitizada<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>{const f=e.target.files?.[0];if(!f)return;if(!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>5000000){setError('Imagem inválida ou maior que 5 MB');return}setImage(URL.createObjectURL(f));setShapes({});setFirst(null)}}/></label>
        <label className="field-label"><input type="checkbox" checked={continuous} onChange={e=>setContinuous(e.target.checked)}/> Propor início automático autorizado</label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">{Object.entries(kinds).map(([k,v])=><button key={k} type="button" aria-pressed={k===kind} className="button-secondary" onClick={()=>{setKind(k);setFirst(null)}}>{v}{shapes[k]?' ✓':''}</button>)}</div>
      <svg viewBox="0 0 1000 600" preserveAspectRatio="none" onClick={mark} className="mt-3 w-full max-w-3xl cursor-crosshair rounded-lg bg-slate-800" aria-label="Área visual de marcação">
        {image?<image href={image} width="1000" height="600" preserveAspectRatio="none"/>:<g><rect x="0" y="100" width="1000" height="400" fill="#475569"/><path d="M0 300H1000" stroke="white" strokeDasharray="20 20" strokeWidth="4"/>{Array.from({length:10},(_,i)=><rect key={i} x="480" y={110+38*i} width="40" height="18" fill="white"/>)}</g>}
        {Object.entries(shapes).map(([k,v])=>k==='line'?<line key={k} x1={v[0]*1000} y1={v[1]*600} x2={v[2]*1000} y2={v[3]*600} stroke="#fbbf24" strokeWidth="5"/>:<rect key={k} x={v[0]*1000} y={v[1]*600} width={(v[2]-v[0])*1000} height={(v[3]-v[1])*600} fill={k.startsWith('approach')?'#38bdf8':'#4ade80'} fillOpacity=".25" stroke="white" strokeWidth="3"><title>{kinds[k]}</title></rect>)}
        {first&&<circle cx={first[0]*1000} cy={first[1]*600} r="8" fill="#fbbf24"/>}
      </svg>
      <p className="mt-2 text-sm">{first?'Selecione o segundo ponto':'Selecione o primeiro ponto'} — {kinds[kind]}</p>
      <div className="mt-3 flex flex-wrap gap-2"><button type="button" className="button-secondary" onClick={()=>{setShapes({});setFirst(null);setImage(null)}}>Limpar marcações</button><button type="button" className="button-secondary" onClick={exportDraft}>Exportar rascunho de calibração</button></div>
      {error&&<p role="alert" className="mt-2 text-amber-200">{error}</p>}
    </details></Panel>
}
