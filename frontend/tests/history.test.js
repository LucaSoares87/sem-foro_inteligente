import test from 'node:test'
import assert from 'node:assert/strict'
import {fetchIntersectionHistory} from '../src/history.js'
import {historyChartModel,seriesKey,splitHistorySegments,summarizeHistory} from '../src/app/historyChart.js'

const points=[
  {ended_at:'2026-11-22T10:00:00+00:00',observed_passages:2,quality:'observed',analytics_epoch:'a'},
  {ended_at:'2026-11-22T10:01:00+00:00',observed_passages:4,quality:'observed',analytics_epoch:'a'},
  {ended_at:'2026-11-22T10:02:00+00:00',observed_passages:3,quality:'limited',analytics_epoch:'a'},
  {ended_at:'2026-11-22T10:03:00+00:00',observed_passages:5,quality:'observed',analytics_epoch:'a'},
  {ended_at:'2026-11-22T10:04:00+00:00',observed_passages:1,quality:'observed',analytics_epoch:'b'}
]

test('history chart breaks at limited windows and epoch changes',()=>{
  const segments=splitHistorySegments(points)
  assert.deepEqual(segments.map(segment=>segment.length),[2,1,1,1])
  const model=historyChartModel(points)
  assert.equal(model.points.length,5)
  assert.equal(model.maxValue,5)
  assert.equal(model.segments.length,4)
  assert.ok(model.points.every(point=>Number.isFinite(point.x)&&Number.isFinite(point.y)))
})

test('history summary remains descriptive and source key is explicit',()=>{
  const summary=summarizeHistory(points)
  assert.equal(summary.latest,1)
  assert.equal(summary.maximum,5)
  assert.equal(summary.mean,3)
  assert.equal(summary.limited,1)
  assert.equal(seriesKey({source_id:'CAM_1',line_id:'L1',direction:'negative_to_positive'}),'CAM_1|L1|negative_to_positive')
  assert.equal(summarizeHistory([]),null)
})

test('history client requires no cross-camera aggregation contract',async()=>{
  const payload={intersection_code:'CR_01',aggregation_across_sources:false,series:[
    {source_id:'CAM_1',line_id:'L1',direction:'negative_to_positive',points:[points[0]]}
  ]}
  const data=await fetchIntersectionHistory('CR_01',undefined,async(url,options)=>{
    assert.equal(url,'/api/v1/predictive/intersections/CR_01/history?limit=60')
    assert.equal(options.cache,'no-store')
    return {status:200,json:async()=>payload}
  })
  assert.equal(data.series.length,1)
  await assert.rejects(fetchIntersectionHistory('CR_01',undefined,async()=>({status:200,json:async()=>({...payload,aggregation_across_sources:true})})))
  await assert.rejects(fetchIntersectionHistory('cr 01',undefined,async()=>({status:200,json:async()=>payload})))
  await assert.rejects(fetchIntersectionHistory('CR_01',undefined,async()=>({status:503,json:async()=>({})})))
})
