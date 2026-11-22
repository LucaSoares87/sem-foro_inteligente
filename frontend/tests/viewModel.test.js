import test from 'node:test'
import assert from 'node:assert/strict'
import { collectAlerts, executiveMetrics, intersectionRows } from '../src/app/viewModel.js'

test('executive metrics preserve missing data instead of fabricating zeros', () => {
  const empty = executiveMetrics(null)
  assert.equal(empty.observedPassages, null)
  assert.equal(empty.visibleTracked, null)

  const noMeasurements = executiveMetrics({ video: { registered: 0, active: 0, sources: [] } })
  assert.equal(noMeasurements.intersections, 0)
  assert.equal(noMeasurements.observedPassages, null)
  assert.equal(noMeasurements.visibleTracked, null)
})

test('executive metrics aggregate only contract-backed values', () => {
  const data = {
    video: { registered: 2, active: 1, sources: [
      { source_id:'CAM_1', intersection_code:'CR_01', state:'running' },
      { source_id:'CAM_2', intersection_code:'CR_02', state:'error' }
    ]},
    tracking: { sources: [
      { source_id:'CAM_1', intersection_code:'CR_01', confirmed_visible:4 },
      { source_id:'CAM_2', intersection_code:'CR_02', confirmed_visible:2 }
    ]},
    analytics: { sources: [
      { source_id:'CAM_1', intersection_code:'CR_01', quality:'experimental', lines:[
        { negative_to_positive:3, positive_to_negative:2 }
      ]}
    ]},
    predictive: { saved:7 }
  }
  const metrics = executiveMetrics(data)
  assert.deepEqual(metrics, {
    intersections:2, sources:2, activeSources:1, visibleTracked:6, observedPassages:5, persistedWindows:7
  })
  const rows = intersectionRows(data)
  assert.equal(rows.length, 2)
  assert.equal(rows[0].code, 'CR_01')
  assert.equal(rows[0].liveSources, 1)
  assert.equal(rows[0].confirmedVisible, 4)
  assert.equal(rows[1].errorSources, 1)
})

test('alerts expose degradation and advisory abstention without inventing incidents', () => {
  const data = {
    status:'degraded',
    video:{ sources:[{source_id:'CAM_2',state:'reconnecting'}] },
    vision:{ state:'error', error_code:'model_load_failed' },
    tracking:{ errors:{CAM_1:'tracking_failed'} },
    analytics:{ errors:{} },
    predictive:{ failed:1,dropped:2 },
    decision:{ operational_decision:'abstain' }
  }
  const alerts = collectAlerts(data,'current','disconnected')
  assert.ok(alerts.some(item => item.title === 'Plataforma degradada'))
  assert.ok(alerts.some(item => item.title === 'Inferência visual indisponível'))
  assert.ok(alerts.some(item => item.title === 'Decisão operacional em abstenção' && item.severity === 'info'))
  assert.ok(alerts.length >= 7)
  assert.deepEqual(collectAlerts({status:'ready',video:{sources:[]}},'current','connected'), [])
})

test('intersection aggregation sums multiple feeds and keeps the most conservative quality', () => {
  const rows = intersectionRows({
    video:{sources:[
      {source_id:'A',intersection_code:'CR_01',state:'running'},
      {source_id:'B',intersection_code:'CR_01',state:'running'}
    ]},
    tracking:{sources:[
      {source_id:'A',intersection_code:'CR_01',confirmed_visible:2},
      {source_id:'B',intersection_code:'CR_01',confirmed_visible:3}
    ]},
    analytics:{sources:[
      {source_id:'A',intersection_code:'CR_01',quality:'experimental'},
      {source_id:'B',intersection_code:'CR_01',quality:'limited_sampling'}
    ]}
  })
  assert.equal(rows.length,1)
  assert.equal(rows[0].sources,2)
  assert.equal(rows[0].liveSources,2)
  assert.equal(rows[0].confirmedVisible,5)
  assert.equal(rows[0].analyticsQuality,'limited_sampling')
})
