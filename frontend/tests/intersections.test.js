import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchIntersections } from '../src/intersections.js'

test('loads explicit geographic registry from same-origin API', async () => {
  const payload=[{code:'CR_01',name:'A x B',district:'Centro',latitude:-8,longitude:-35,enabled:true,has_coordinates:true}]
  const result=await fetchIntersections(undefined,async (url,options)=>{
    assert.equal(url,'/api/v1/intersections')
    assert.equal(options.cache,'no-store')
    return {status:200,json:async()=>payload}
  })
  assert.deepEqual(result,payload)
})

test('rejects invalid registry transport and inconsistent coordinate contract', async () => {
  await assert.rejects(fetchIntersections(undefined,async()=>({status:503,json:async()=>[]})))
  await assert.rejects(fetchIntersections(undefined,async()=>({status:200,json:async()=>({})})))
  await assert.rejects(fetchIntersections(undefined,async()=>({status:200,json:async()=>[
    {code:'CR_01',name:'A',enabled:true,latitude:-8,longitude:-35,has_coordinates:false}
  ]})))
})
