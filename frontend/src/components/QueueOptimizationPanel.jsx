import React from 'react'
import useQueueOptimization from '../useQueueOptimization.js'
import {optimizationReason} from '../queueOptimization.js'
import {EmptyState,Panel,SectionHeading,StatusPill} from './ui.jsx'

const fmt=(value,digits=2)=>Number.isFinite(value)?value.toLocaleString('pt-BR',{maximumFractionDigits:digits}):'—'
const preferred=value=>({
  minor_first:'Fila menor primeiro',
  major_first:'Fluxo dominante primeiro',
  no_material_advantage:'Sem vantagem material',
  abstain:'Abstenção'
}[value]||value)

function ApproachCard({approach}){
  return <article className="info-block">
    <div className="flex items-start justify-between gap-2">
      <div><span>{approach.approach_id} · grupo {approach.service_group}</span>
        <strong>{approach.queue_length} em fila</strong></div>
      <StatusPill value={approach.quality}/>
    </div>
    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
      <div><dt className="text-slate-600">Chegada</dt><dd className="text-slate-300">{fmt(approach.arrival_rate_vps)} veh/s</dd></div>
      <div><dt className="text-slate-600">Descarga</dt><dd className="text-slate-300">{fmt(approach.discharge_rate_vps)} veh/s</dd></div>
      <div><dt className="text-slate-600">Espera média</dt><dd className="text-slate-300">{fmt(approach.mean_wait_seconds,1)} s</dd></div>
      <div><dt className="text-slate-600">Espera máxima</dt><dd className="text-slate-300">{fmt(approach.max_wait_seconds,1)} s</dd></div>
      <div><dt className="text-slate-600">Ocupação da capacidade</dt><dd className="text-slate-300">{fmt(100*approach.storage_occupancy_ratio,1)}%</dd></div>
      <div><dt className="text-slate-600">Confiança</dt><dd className="text-slate-300">{fmt(100*approach.observation_confidence,1)}%</dd></div>
    </dl>
  </article>
}

function DecisionCard({result}){
  return <article className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-xs uppercase tracking-[.12em] text-slate-500">Contrafactual SI-09</p>
        <h3 className="mt-2 text-lg font-semibold text-slate-100">{preferred(result.preferred_in_simulation)}</h3>
        <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">{optimizationReason(result.reason)}</p>
      </div>
      <StatusPill value={result.state}/>
    </div>
    {result.major_group&&result.minor_group&&<div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="queue-stat"><span>Fila maior</span><strong>{result.major_group.group_id}: {result.major_group.queue_length}</strong></div>
      <div className="queue-stat"><span>Fila menor</span><strong>{result.minor_group.group_id}: {result.minor_group.queue_length}</strong></div>
      <div className="queue-stat"><span>X dinâmico seguro</span><strong>{result.dynamic_x_safe_vehicles??'—'}</strong></div>
      <div className="queue-stat"><span>Tempo analítico de limpeza</span><strong>{result.minor_clearance_seconds==null?'—':fmt(result.minor_clearance_seconds,1)+' s'}</strong></div>
    </div>}
    {result.minor_first&&result.major_first&&<div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[620px] text-left text-xs">
        <thead className="text-slate-600"><tr><th className="py-2">Cenário</th><th>Custo</th><th>Fila·s</th><th>Spillback·s</th><th>Interrupção de fluxo</th><th>Espera máx. proxy</th></tr></thead>
        <tbody className="border-t border-slate-800 text-slate-300">
          <tr><td className="py-2">Menor → maior</td><td>{fmt(result.minor_first.total_cost,1)}</td><td>{fmt(result.minor_first.queue_area_vehicle_seconds,1)}</td><td>{fmt(result.minor_first.spillback_exposure_vehicle_seconds,1)}</td><td>{fmt(result.minor_first.flow_interruption_proxy,1)}</td><td>{fmt(result.minor_first.max_wait_proxy_seconds,1)} s</td></tr>
          <tr><td className="py-2">Maior → menor</td><td>{fmt(result.major_first.total_cost,1)}</td><td>{fmt(result.major_first.queue_area_vehicle_seconds,1)}</td><td>{fmt(result.major_first.spillback_exposure_vehicle_seconds,1)}</td><td>{fmt(result.major_first.flow_interruption_proxy,1)}</td><td>{fmt(result.major_first.max_wait_proxy_seconds,1)} s</td></tr>
        </tbody>
      </table>
    </div>}
    <p className="mt-4 text-[11px] leading-5 text-amber-300">Preferência exclusivamente simulada. Os pesos da função de custo ainda são de engenharia e não homologados. Nenhum tempo exibido é comando de controlador.</p>
  </article>
}

export default function QueueOptimizationPanel({intersection}){
  const {data,status}=useQueueOptimization()
  if(status==='loading'&&!data) return <Panel><p className="text-sm text-slate-400">Carregando inteligência de filas...</p></Panel>
  if(status==='error'&&!data) return <Panel><EmptyState title="Inteligência de filas indisponível" description="A API protegida não respondeu; nenhum valor foi inferido pela interface."/></Panel>
  const sources=(data?.queue?.sources||[]).filter(source=>!intersection||source.intersection_code===intersection)
  const decisions=new Map((data?.optimization?.sources||[]).map(result=>[result.source_id,result]))
  return <Panel>
    <SectionHeading eyebrow="Queue Intelligence · SI-09" title={intersection?'Filas e X dinâmico — '+intersection:'Filas e X dinâmico'}
      description="Estima fila, chegada, descarga e espera a partir dos tracks. Compara menor→maior e maior→menor sem enviar comandos físicos."/>
    {!sources.length?<EmptyState title="Sem estado de fila disponível" description="Configure approaches em TRAFFIC_GEOMETRY_JSON e aguarde tracking/analytics atuais. A plataforma não converte ausência de observação em fila zero."/>:
      <div className="space-y-5">{sources.map(source=><section key={source.source_id} className="rounded-xl border border-slate-800 bg-slate-950/25 p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-medium text-slate-200">{source.source_id}</p>
            <p className="mt-1 text-xs text-slate-500">Origem: {source.data_origin} · velocidade física: não calibrada</p></div>
          {source.data_origin==='external_real_replay'&&!source.commercial_demo_authorized&&
            <span className="status-pill border-amber-400/25 bg-amber-400/10 text-amber-200">Uso comercial não autorizado</span>}
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{source.approaches.map(item=><ApproachCard key={item.approach_id} approach={item}/>)}</div>
        <div className="mt-4"><DecisionCard result={decisions.get(source.source_id)||{
          state:'abstain',preferred_in_simulation:'abstain',reason:'requires_two_service_groups'
        }}/></div>
      </section>)}</div>}
    {status==='error'&&data&&<p className="mt-3 text-xs text-amber-300">A atualização recente falhou; exibindo a última leitura válida.</p>}
  </Panel>
}
