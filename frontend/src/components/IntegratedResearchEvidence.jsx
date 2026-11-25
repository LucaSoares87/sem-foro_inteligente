import React from 'react'
import {Panel,SectionHeading} from './ui.jsx'
import {integratedEvidence,validateIntegratedEvidence} from '../app/integratedEvidence.js'
const repo='https://github.com/LucaSoares87/sem-foro_inteligente'
export default function IntegratedResearchEvidence(){
  if(!validateIntegratedEvidence(integratedEvidence))return <Panel><p>Acervo integrado indisponível — contrato inválido.</p></Panel>
  return <Panel>
    <section aria-label="Acervo integrado do ciclo I">
      <SectionHeading eyebrow="I-CLOSE · Acervo de pesquisa" title="Ciclo I — evidências integradas" description="Extrato arquivado de ensaios sintéticos e testes de software; não é telemetria atual nem homologação de campo. Os motores experimentais permanecem isolados."/>
      <div className="flex flex-wrap gap-2 text-xs text-amber-200">
        {['Nenhum candidato promovido','C3: referência independente bloqueada','Soak 24h não executado','Agendamento não instalado','Aceite humano pendente'].map(s=><span key={s} className="rounded-lg border border-amber-400/20 px-3 py-2">{s}</span>)}
      </div>
      <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {integratedEvidence.studies.map(s=><article key={s.id} className="min-w-0 rounded-xl border border-slate-800 p-4">
          <p className="text-xs text-sky-300">{s.id} — {s.label}</p>
          <h3 className="mt-2 font-semibold text-slate-100">{s.status}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-300">{s.result}</p>
          <p className="mt-2 text-xs leading-5 text-slate-400">{s.limit}</p>
          <details className="mt-3 text-xs text-slate-400"><summary>Proveniência</summary>
            <p className="mt-2 break-all">{s.digest?'Relatório SHA-256: '+s.digest:'Evidência JUnit — não há relatório histórico real.'}</p>
            <a className="mt-2 block text-sky-300 underline" href={repo+'/actions/runs/'+s.run} target="_blank" rel="noreferrer">Execução original · artefato {s.artifact}</a>
          </details>
        </article>)}
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-400">Velocidade física, disponibilidade municipal e benefícios reais continuam não validados. Consulte os protocolos e artefatos originais; a retenção de artefatos pode expirar. As sugestões científicas não aplicam parâmetros nem instalam agendamento.</p>
      <a className="mt-3 inline-block text-sm text-sky-300 underline" href={repo+'/blob/research/pimcat-i-close-integrated-intelligence/docs/final-acceptance/i-close-integrated-audit.md'} target="_blank" rel="noreferrer">Dossiê de auditoria e homologação</a>
    </section>
  </Panel>
}
