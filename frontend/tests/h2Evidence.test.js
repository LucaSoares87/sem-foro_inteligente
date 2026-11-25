import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
const d=JSON.parse(readFileSync(new URL('../src/app/h2Evidence.json',import.meta.url)))
test('H2 extract retains the negative scientific result and no field authority',()=>{
 assert.equal(d.cases,24);assert.equal(d.trajectories,96)
 assert.equal(d.research_gate_passed,false);assert.equal(d.candidate_promoted,false);assert.equal(d.physical_actuation,false)
 assert.equal(d.c3_independent_precision,'BLOCKED_BY_INDEPENDENT_ANNOTATION')
 assert.equal(d.gates.mid,false);assert.equal(d.gates.cross,false);assert.equal(d.gates.stress,false)
 const a=d.rows.find(r=>r[0]==='compatible'),b=d.rows.find(r=>r[0]==='gap_guarded')
 assert.ok(b[d.metrics.indexOf('a_stops')+1]<a[d.metrics.indexOf('a_stops')+1])
 assert.ok(b[d.metrics.indexOf('pedestrian_area')+1]>a[d.metrics.indexOf('pedestrian_area')+1])
})
