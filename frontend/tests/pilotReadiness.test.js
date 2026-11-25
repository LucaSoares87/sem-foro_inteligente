import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {pilotReadiness,healthReading,matchingDecision,requiredGates} from '../src/app/pilotReadiness.js'
const complete={state:'available',framework_ready:true,pilot_ready:true,pilot_decision:'ready_for_supervised_pilot',missing_evidence:[],physical_actuation:false,operational_decision:'abstain',
  gates:requiredGates.map(gate=>({gate,state:'ready',origin:'field',artifact_sha256:'a'.repeat(64),reference:'fixture',executed_at:'2026-01-01T00:00:00Z'}))}
test('only current complete scorecard can show readiness',()=>{
  assert.equal(pilotReadiness(complete,'current').state,'ready')
  assert.equal(pilotReadiness(complete,'error').state,'unknown')
  assert.equal(pilotReadiness(complete,'loading').readyCount,null)
  assert.equal(pilotReadiness({...complete,pilot_ready:false},'current').state,'blocked')
  assert.equal(pilotReadiness({...complete,gates:complete.gates.slice(1)},'current').state,'blocked')
  assert.equal(pilotReadiness({...complete,gates:[...complete.gates,complete.gates[0]]},'current').state,'blocked')
  assert.equal(pilotReadiness({...complete,gates:complete.gates.map(g=>({...g,origin:'synthetic'}))},'current').readyCount,0)
  assert.equal(pilotReadiness({...complete,physical_actuation:true},'current').state,'unknown')
})
test('health unavailable is not a current reading',()=>{
  assert.equal(healthReading({status:'ready',timestamp:'2026-01-01T00:00:00Z'},'error').timestamp,null)
  assert.equal(healthReading({status:'ready',timestamp:'bad'},'current').timestamp,null)
})
test('do not infer preferences from different or missing frames',()=>{
  const source={source_id:'s',intersection_code:'i',frame_sequence:2}
  const decision={...source,physical_actuation:false,operationally_validated:false,operational_decision:'abstain'}
  assert.equal(matchingDecision(source,decision),decision)
  assert.equal(matchingDecision(source,null),null)
  assert.equal(matchingDecision(source,{...decision,frame_sequence:1}),null)
  assert.equal(matchingDecision(source,{...decision,intersection_code:'j'}),null)
  assert.equal(matchingDecision(source,{...decision,physical_actuation:true}),null)
})
test('archived evidence is explicitly synthetic with original hashes and no promotion',()=>{
  const d=JSON.parse(readFileSync(new URL('../src/app/researchEvidence.json',import.meta.url)))
  assert.equal(d.scope,'archived_synthetic_aggregate_extract')
  assert.equal(d.origin,'synthetic')
  assert.deepEqual(d.studies.map(s=>s.id),['SI-11A','SI-11B','SI-11C','SI-11D'])
  assert.equal(d.studies.reduce((n,s)=>n+s.trajectories,0),7488)
  for(const s of d.studies){
    assert.equal(s.origin,'synthetic')
    assert.equal(s.physical_actuation,false)
    assert.equal(s.candidate_promoted,false)
    assert.notEqual(s.research_gate_passed,true)
    for(const key of ['zip_sha256','report_sha256'])assert.match(s[key],/^[a-f0-9]{64}$/)
    for(const row of s.rows){
      assert.equal(row.values.length,s.metrics.length)
      assert.ok(row.values.every(v=>Number.isFinite(v)&&v>=0))
    }
  }
  const sumo=d.studies.at(-1)
  assert.deepEqual(sumo.rows[2].values,sumo.rows[3].values)
  assert.equal(sumo.rows[1].values[0],2808.1875)
})
