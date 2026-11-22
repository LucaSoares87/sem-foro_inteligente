import React from 'react'
import { displayStatus } from '../health.js'

const toneClasses = {
  good: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
  warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  critical: 'border-rose-400/25 bg-rose-400/10 text-rose-200',
  info: 'border-sky-400/25 bg-sky-400/10 text-sky-200',
  neutral: 'border-slate-700 bg-slate-800/60 text-slate-200'
}

export function Panel({ children, className = '', as: Tag = 'section' }) {
  return <Tag className={'surface-panel ' + className}>{children}</Tag>
}

export function SectionHeading({ eyebrow, title, description, action }) {
  return <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
    <div className="min-w-0">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-50 sm:text-xl">{title}</h2>
      {description && <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{description}</p>}
    </div>
    {action}
  </div>
}

export function MetricCard({ label, value, detail, tone = 'neutral' }) {
  return <article className="metric-card">
    <div className="flex items-start justify-between gap-3">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <span aria-hidden="true" className={'h-2 w-2 rounded-full ' + (tone === 'good' ? 'bg-emerald-300' : tone === 'warning' ? 'bg-amber-300' : tone === 'critical' ? 'bg-rose-300' : 'bg-sky-300')} />
    </div>
    <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-50">{value}</p>
    {detail && <p className="mt-2 text-xs leading-5 text-slate-500">{detail}</p>}
  </article>
}

export function StatusPill({ value, label }) {
  const tone = ['online','current','available','ready','running','simulation_available'].includes(value)
    ? 'good' : ['degraded','reconnecting','limited_sampling','loading','starting'].includes(value)
      ? 'warning' : ['offline','error'].includes(value) ? 'critical' : 'neutral'
  return <span className={'status-pill ' + toneClasses[tone]}>{label || displayStatus(value)}</span>
}

export function AlertRow({ alert }) {
  return <li className={'rounded-xl border px-4 py-3 ' + toneClasses[alert.severity] }>
    <p className="text-sm font-medium">{alert.title}</p>
    <p className="mt-1 text-xs leading-5 opacity-80">{alert.detail}</p>
  </li>
}

export function EmptyState({ title, description }) {
  return <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/30 px-5 py-8 text-center">
    <p className="text-sm font-medium text-slate-300">{title}</p>
    {description && <p className="mx-auto mt-2 max-w-xl text-xs leading-5 text-slate-500">{description}</p>}
  </div>
}

export function DataTable({ columns, rows, rowKey }) {
  return <div className="overflow-x-auto">
    <table className="w-full min-w-[640px] text-left text-sm">
      <thead className="border-b border-slate-800 text-xs uppercase tracking-[0.1em] text-slate-500">
        <tr>{columns.map(column => <th key={column.key} scope="col" className="px-3 py-3 font-medium">{column.label}</th>)}</tr>
      </thead>
      <tbody>{rows.map(row => <tr key={rowKey(row)} className="border-b border-slate-800/70 last:border-0">
        {columns.map(column => <td key={column.key} className="px-3 py-3 text-slate-300">{column.render ? column.render(row) : row[column.key]}</td>)}
      </tr>)}</tbody>
    </table>
  </div>
}
