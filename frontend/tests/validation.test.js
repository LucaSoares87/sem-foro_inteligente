import test from 'node:test'
import assert from 'node:assert/strict'
import {fetchValidation} from '../src/validation.js'

const payload={
  state:'available',framework_ready:true,pilot_ready:false,
  pilot_decision:'blocked_by_field_evidence',
  missing_evidence:['physical_camera'],
  runtime_observation:{authorized_candidate_model_loaded:false,physical_sources_configured:0,physical_sources_running:0},
  gates:[{gate:'physical_camera',state:'blocked',origin:null,reference:null,artifact_sha256:null,executed_at:null,note:'pending'}],
  error_code:null,physical_actuation:false,operational_decision:'abstain'
}

test('loads protected validation scorecard contract',async()=>{
  const data=await fetchValidation(undefined,async(url,options)=>{
    assert.equal(url,'/api/v1/validation/status')
    assert.equal(options.cache,'no-store')
    return {status:200,json:async()=>payload}
  })
  assert.equal(data.pilot_ready,false)
  assert.equal(data.gates[0].state,'blocked')
})

test('rejects invalid or unauthorized validation responses',async()=>{
  await assert.rejects(fetchValidation(undefined,async()=>({status:401,json:async()=>({})})))
  await assert.rejects(fetchValidation(undefined,async()=>({status:200,json:async()=>({...payload,physical_actuation:true})})))
  await assert.rejects(fetchValidation(undefined,async()=>({status:200,json:async()=>({...payload,gates:{}})})))
})
