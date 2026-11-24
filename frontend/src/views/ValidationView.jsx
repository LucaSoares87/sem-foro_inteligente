import React from 'react'
import {displayStatus} from '../health.js'
import {EmptyState,Panel,SectionHeading,StatusPill} from '../components/ui.jsx'

const labels={
  synthetic_demo_dataset:'Dataset sintético de demonstração',
  authorized_model:'Modelo autorizado + métricas',
  physical_camera:'Câmera física autorizada',
  calibration:'Calibração do cruzamento',
  field_ground_truth:'Ground truth de campo',
  hardware_benchmark:'Benchmark no hardware-alvo',
  recovery_drill:'Recovery drill no hardware-alvo',
  human_acceptance:'Aceite humano'
}
const pilotRequired=new Set([
  'authorized_model','physical_camera','calibration','field_ground_truth',
  'hardware_benchmark','recovery_drill','human_acceptance'
])

function shortHash(value){
  return value ? value.slice(0,10)+'…'+value.slice(-6) : '—'
}

export default function ValidationView({data}){
  const validation=data?.validation
  if(!validation) return <EmptyState title="Homologação indisponível" description="O contrato de validação ainda não foi carregado pelo backend."/>
  const runtime=validation.runtime_observation||{}
  const missing=new Set(validation.missing_evidence||[])
  return <div className="space-y-6">
    <section className="hero-band">
      <p className="eyebrow">SI-08B · Homologação integrada</p>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">Preparação do piloto supervisionado</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">O scorecard diferencia capacidade de software de evidência de campo. Nenhum gate é aprovado apenas porque a interface ou o motor estão funcionando.</p>
        </div>
        <StatusPill value={validation.pilot_decision}/>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <StatusPill value={validation.framework_ready?'ready':'error'} label={'Framework: '+(validation.framework_ready?'pronto':'inválido')}/>
        <span className="status-pill border-slate-700 bg-slate-800/60 text-slate-200">Atuação física: desabilitada</span>
        <span className="status-pill border-slate-700 bg-slate-800/60 text-slate-200">Decisão: abstenção</span>
      </div>
    </section>

    <Panel>
      <SectionHeading eyebrow="Gate final" title={validation.pilot_ready?'Pronto para piloto supervisionado':'Ainda não aprovado para piloto'}
        description={validation.pilot_ready
          ? 'Todas as evidências obrigatórias foram declaradas e o aceite humano foi registrado.'
          : (validation.missing_evidence?.length||0)+' evidência(s) obrigatória(s) ainda não estão prontas.'}/>
      {!validation.pilot_ready&&<div className="rounded-xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm leading-6 text-amber-100">
        A aplicação permanece demonstrável e consultiva, mas o piloto não deve ser apresentado como homologado enquanto os gates de campo abaixo estiverem pendentes.
      </div>}
    </Panel>

    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {(validation.gates||[]).map(gate=><article key={gate.gate} className="metric-card">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-slate-500">{pilotRequired.has(gate.gate)?'Obrigatório para piloto':'Demonstração'}</p>
            <h2 className="mt-2 text-base font-semibold text-slate-100">{labels[gate.gate]||gate.gate}</h2>
          </div>
          <StatusPill value={gate.state}/>
        </div>
        <p className="mt-3 min-h-10 text-xs leading-5 text-slate-500">{gate.note}</p>
        <dl className="mt-4 space-y-2 border-t border-slate-800 pt-3 text-xs">
          <div className="flex justify-between gap-3"><dt className="text-slate-600">Origem</dt><dd className="text-right text-slate-400">{gate.origin||'—'}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-slate-600">Artefato</dt><dd className="font-mono text-right text-slate-400">{shortHash(gate.artifact_sha256)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-slate-600">Evidência</dt><dd className="max-w-44 truncate text-right text-slate-400" title={gate.reference||''}>{gate.reference||'—'}</dd></div>
        </dl>
        {missing.has(gate.gate)&&<p className="mt-3 text-[11px] font-medium text-amber-300">Ainda bloqueia o piloto.</p>}
      </article>)}
    </section>

    <div className="grid gap-6 xl:grid-cols-2">
      <Panel>
        <SectionHeading eyebrow="Observação de runtime" title="Ativos disponíveis agora" description="Configuração atual não substitui evidência formal de homologação."/>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="info-block"><span>Modelo candidato</span><strong>{runtime.authorized_candidate_model_loaded?'Carregado':'Não'}</strong><small>Purpose authorized_candidate</small></div>
          <div className="info-block"><span>Fontes físicas</span><strong>{runtime.physical_sources_configured??0}</strong><small>Webcam/RTSP configuradas</small></div>
          <div className="info-block"><span>Fontes rodando</span><strong>{runtime.physical_sources_running??0}</strong><small>Snapshot atual</small></div>
        </div>
      </Panel>
      <Panel>
        <SectionHeading eyebrow="Interpretação" title="O que este scorecard significa" description="Métricas e evidências são independentes da decisão operacional."/>
        <ul className="space-y-3 text-sm leading-6 text-slate-400">
          <li>Um relatório de avaliação pode atingir os thresholds fornecidos e ainda assim não autoriza operação municipal.</li>
          <li>Evidência sintética nunca satisfaz os gates de campo obrigatórios.</li>
          <li>O aceite humano é obrigatório e não pode ser marcado automaticamente pela aplicação.</li>
          <li>Mesmo com todos os gates prontos, a plataforma permanece sem atuação física nesta arquitetura.</li>
        </ul>
      </Panel>
    </div>

    {validation.error_code&&<Panel>
      <SectionHeading title="Configuração de evidência inválida" description={displayStatus(validation.state)}/>
      <p className="text-sm text-rose-300">{validation.error_code}</p>
    </Panel>}
  </div>
}
