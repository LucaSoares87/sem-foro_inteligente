import test from 'node:test'
import assert from 'node:assert/strict'
import {fetchQueueOptimization,optimizationReason} from '../src/queueOptimization.js'

const queue={state:'available',sources:[],physical_speed_available:false,
  operationally_validated:false,decision_mode:'simulation_only'}
const optimization={state:'idle',sources:[],physical_actuation:false,
  operationally_validated:false,operational_decision:'abstain',engineering_weights_validated:false}

test('loads queue and optimization contracts without physical actuation',async()=>{
  const calls=[]
  const data=await fetchQueueOptimization(undefined,async(url,options)=>{
    calls.push([url,options.cache])
    return {status:200,json:async()=>url.includes('/queue/')?queue:optimization}
  })
  assert.deepEqual(calls,[
    ['/api/v1/queue/status','no-store'],
    ['/api/v1/optimization/status','no-store']
  ])
  assert.equal(data.queue.physical_speed_available,false)
  assert.equal(data.optimization.operational_decision,'abstain')
})

test('rejects unsafe contracts and explains dynamic X decisions',async()=>{
  await assert.rejects(fetchQueueOptimization(undefined,async url=>({
    status:200,json:async()=>url.includes('/queue/')?queue:{...optimization,physical_actuation:true}
  })))
  assert.match(optimizationReason('minor_exceeds_dynamic_x'),/X dinâmico/)
  assert.match(optimizationReason('minor_first_lower_cost'),/esvaziada primeiro/)
})
