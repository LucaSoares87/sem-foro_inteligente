import test from 'node:test'
import assert from 'node:assert/strict'
import { filterIntersections, mapPoints, mapProjection, operationalRows } from '../src/app/geography.js'

test('merges registered and operational-only intersections without inventing geography', () => {
  const registry=[
    {code:'CR_01',name:'A x B',district:'Centro',latitude:-8,longitude:-35,has_coordinates:true,enabled:true},
    {code:'CR_03',name:'Cadastro sem câmera',district:null,latitude:null,longitude:null,has_coordinates:false,enabled:true}
  ]
  const data={
    video:{sources:[
      {source_id:'A',intersection_code:'CR_01',state:'running'},
      {source_id:'B',intersection_code:'CR_02',state:'error'}
    ]},
    tracking:{sources:[{source_id:'A',intersection_code:'CR_01',confirmed_visible:3}]},
    analytics:{sources:[{source_id:'A',intersection_code:'CR_01',quality:'experimental'}]}
  }
  const rows=operationalRows(registry,data)
  assert.equal(rows.length,3)
  assert.equal(rows.find(r=>r.code==='CR_01').confirmedVisible,3)
  const missing=rows.find(r=>r.code==='CR_02')
  assert.equal(missing.registered,false)
  assert.equal(missing.has_coordinates,false)
  assert.equal(rows.find(r=>r.code==='CR_03').sources,0)
})

test('map only projects explicit finite WGS84 pairs and handles one point', () => {
  const rows=[
    {code:'A',name:'A',latitude:-8,longitude:-35,has_coordinates:true},
    {code:'B',name:'B',latitude:null,longitude:null,has_coordinates:false}
  ]
  assert.deepEqual(mapPoints(rows).map(x=>x.code),['A'])
  const projected=mapProjection(rows)
  assert.equal(projected.length,1)
  assert.ok(Number.isFinite(projected[0].x)&&Number.isFinite(projected[0].y))
  assert.ok(projected[0].x>0&&projected[0].x<1000)
})

test('search and district filters use registered metadata', () => {
  const rows=[
    {code:'CR_01',name:'Av Norte x Rua A',district:'Norte'},
    {code:'CR_02',name:'Av Sul x Rua B',district:'Sul'}
  ]
  assert.deepEqual(filterIntersections(rows,'norte','').map(x=>x.code),['CR_01'])
  assert.deepEqual(filterIntersections(rows,'','Sul').map(x=>x.code),['CR_02'])
  assert.equal(filterIntersections(rows,'inexistente','').length,0)
})
