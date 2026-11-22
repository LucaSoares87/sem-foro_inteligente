import React from 'react'
import { mapProjection } from '../app/geography.js'

function markerTone(point){
  if(point.errorSources>0) return 'geo-marker-error'
  if(point.liveSources>0) return 'geo-marker-live'
  return 'geo-marker-idle'
}

export default function GeoOverview({rows,onOpen}){
  const points=mapProjection(rows)
  if(!points.length) return <div className="map-placeholder" role="img" aria-label="Nenhum cruzamento com coordenadas WGS84 cadastrado">
    <div><p className="text-sm font-medium text-slate-300">Sem coordenadas cadastradas</p>
      <p className="mt-1 text-xs text-slate-500">O mapa só exibe coordenadas explícitas do registro de cruzamentos.</p></div>
  </div>
  return <div>
    <div className="geo-map" role="img" aria-label={'Mapa vetorial WGS84 com '+points.length+' cruzamento(s) cadastrado(s)'}>
      <svg viewBox="0 0 1000 460" className="h-full w-full" preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="geo-grid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M 50 0 L 0 0 0 50" fill="none" stroke="currentColor" strokeOpacity=".13" strokeWidth="1"/>
          </pattern>
        </defs>
        <rect width="1000" height="460" fill="url(#geo-grid)" className="text-slate-500"/>
        {points.map(point=><g key={point.code} transform={'translate('+point.x+' '+point.y+')'}>
          <circle r="16" className={'geo-marker '+markerTone(point)} />
          <circle r="5" className="fill-slate-950" />
          <text x="22" y="-5" className="fill-slate-200 text-[18px] font-semibold">{point.code}</text>
          <text x="22" y="15" className="fill-slate-500 text-[13px]">{point.name}</text>
        </g>)}
      </svg>
      <div className="geo-map-badge">WGS84 · sem mapa-base externo</div>
    </div>
    <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {points.map(point=><button type="button" key={point.code} onClick={()=>onOpen?.(point.code)}
        className="geo-location-card">
        <span><strong>{point.code}</strong><small>{point.name}</small></span>
        <span className="text-right"><small>{point.district||'Distrito não informado'}</small><small>{point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</small></span>
      </button>)}
    </div>
  </div>
}
