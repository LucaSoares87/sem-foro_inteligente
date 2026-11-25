import test from 'node:test'
import assert from 'node:assert/strict'
import {rectangle,buildDraft} from '../src/app/cameraDraft.js'
test('normalized draft has no secret, approval or application',()=>{
  const rect=rectangle([.6,.5],[.1,.1])
  const shapes=Object.fromEntries(['approach_a','approach_b','waiting_a','waiting_b','crossing'].map(k=>[k,rect]))
  shapes.line=[.2,.2,.8,.2]
  const args={source:'CAM_01',code:'CR_01',topology:'midblock',shapes,distance:20,continuous:true}
  const d=buildDraft(args)
  assert.equal(d.status,'draft_not_applied');assert.equal(d.field_authorized,false)
  assert.equal(d.physical_actuation,false);assert.equal(d.geometry_candidate.regions.length,2)
  assert.equal(d.source_registration.requires_external_locator,true)
  assert.throws(()=>buildDraft({...args,source:'rtsp://secret'}))
  assert.throws(()=>buildDraft({...args,distance:0}))
  assert.throws(()=>rectangle([0,0],[0,0]))
})
