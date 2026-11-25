import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {validateLedger,level} from '../src/app/pimcatEvidence.js'
import {fetchDaily,valueText} from '../src/app/dailyReport.js'
const ledger=JSON.parse(readFileSync(new URL('../src/app/pimcatEvidence.json',import.meta.url)))
test('nine verified study extracts preserve origin, gates and no promotion',()=>{
  assert.equal(validateLedger(ledger),true)
  assert.equal(ledger.studies.reduce((a,s)=>a+(s.trajectories??0),0),8576)
  assert.equal(ledger.studies.find(s=>s.key==='c3').origin,'external_real_replay')
  assert.ok(ledger.studies.filter(s=>s.key!=='c3').every(s=>s.origin==='synthetic'))
  assert.equal(ledger.studies.filter(s=>s.research_gate_passed===false).length,7)
  assert.equal(validateLedger({...ledger,candidate_promoted:true}),false)
  const altered=structuredClone(ledger);altered.suggestions[0].applied=true
  assert.equal(validateLedger(altered),false)
})
test('history preserves outage and known zero',()=>{
  const h=ledger.criticity_history
  assert.deepEqual(h.snapshots.map(s=>s.index.filter(x=>level(x)==='critical').length),[3,0,1])
  assert.equal(h.snapshots[1].index.filter(x=>level(x)==='unknown').length,18)
  assert.equal(level(0),'free');assert.equal(level(null),'unknown')
  assert.equal(valueText(null),'—');assert.equal(valueText(0),'0')
})
test('daily contract rejects stale context, invented totals and missing flags',async()=>{
  const d={schema_version:1,intersection_code:'CR_01',date:'2026-01-01',timezone:'America/Sao_Paulo',state:'empty',
    origin:'observed_analytics_source_origin_unverified',aggregation_across_sources:false,operationally_validated:false,
    physical_actuation:false,operational_decision:'abstain',network_total:null,extrapolated:false,series:[],sources:[],report_sha256:'a'.repeat(64)}
  const fetcher=payload=>async()=>({status:200,json:async()=>payload})
  assert.equal(await fetchDaily('CR_01',d.date,null,fetcher(d)),d)
  for(const change of [{intersection_code:'CR_02'},{network_total:0},{physical_actuation:true},{origin:'synthetic'}])
    await assert.rejects(fetchDaily('CR_01',d.date,null,fetcher({...d,...change})))
})
