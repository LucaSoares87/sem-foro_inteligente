import ResearchEvidence from '../components/ResearchEvidence.jsx'
import React from 'react'
import DecisionPanel from '../DecisionPanel.jsx'
import { Panel, SectionHeading } from '../components/ui.jsx'

export default function LaboratoryView({ data }) {
  return <div className="space-y-6">
    <section>
      <p className="eyebrow">Laboratório de Simulação</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Comparação consultiva de políticas</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Ambiente isolado dos dados operacionais para comparar cenários sintéticos de forma reprodutível e explicável.</p>
    </section>
    <Panel>
      <SectionHeading title="Separação de segurança" description="O laboratório não recebe parâmetros físicos de controladores e não converte automaticamente medições reais em plano semafórico." />
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="info-block"><span>Origem</span><strong>Sintética</strong><small>Cenários declarados pelo simulador.</small></div>
        <div className="info-block"><span>Atuação física</span><strong>Desabilitada</strong><small>Não há interface com controladores.</small></div>
        <div className="info-block"><span>Decisão operacional</span><strong>Abstenção</strong><small>Até calibração e revisão independente.</small></div>
      </div>
    </Panel>
    <ResearchEvidence/>
    <DecisionPanel availability={data?.decision} sources={data?.analytics?.sources || []} />
  </div>
}
