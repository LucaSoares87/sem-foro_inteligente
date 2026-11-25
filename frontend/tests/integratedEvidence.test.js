import test from 'node:test'
import assert from 'node:assert/strict'
import {integratedEvidence as evidence,validateIntegratedEvidence as validate} from '../src/app/integratedEvidence.js'
test('I-CLOSE keeps negative and null scientific outcomes, no field promotion',()=>{
  assert.equal(validate(evidence),true)
  assert.deepEqual(evidence.studies.slice(0,4).map(s=>s.outcome),['marginal_pass','failed','failed','null_failed'])
  for(const key of ['physical_actuation','candidate_promoted','operationally_validated','scheduler_installed']){
    assert.equal(validate({...evidence,[key]:true}),false)
  }
  const altered=structuredClone(evidence);altered.studies[3].outcome='synthetic_pass'
  assert.equal(validate(altered),false)
  assert.equal(validate({...evidence,studies:evidence.studies.slice(1)}),false)
})
