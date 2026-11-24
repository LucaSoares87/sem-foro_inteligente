import test from 'node:test'
import assert from 'node:assert/strict'
import { isKnownRoute, normalizePath, routeById, routeFromPath, shouldHandleNavigation, workspaceUrl } from '../src/app/navigation.js'

test('normalizes and resolves all application workspaces', () => {
  assert.equal(normalizePath('/operacional/'), '/operacional')
  assert.equal(routeFromPath('/').id, 'executive')
  assert.equal(routeFromPath('/executivo').id, 'executive')
  assert.equal(routeFromPath('/operacional/').id, 'operations')
  assert.equal(routeFromPath('/laboratorio').id, 'laboratory')
  assert.equal(routeFromPath('/videowall').id, 'videowall')
  assert.equal(routeFromPath('/apresentacao').id, 'presentation')
  assert.equal(routeFromPath('/homologacao').id, 'validation')
})

test('unknown routes fail safely to executive without being considered known', () => {
  assert.equal(isKnownRoute('/qualquer'), false)
  assert.equal(routeFromPath('/qualquer').id, 'executive')
  assert.equal(routeById('missing').id, 'executive')
})

test('client navigation preserves browser modifier behavior', () => {
  assert.equal(shouldHandleNavigation({ button: 0 }), true)
  assert.equal(shouldHandleNavigation({ button: 1 }), false)
  assert.equal(shouldHandleNavigation({ button: 0, ctrlKey: true }), false)
  assert.equal(shouldHandleNavigation({ button: 0, metaKey: true }), false)
  assert.equal(shouldHandleNavigation({ button: 0, shiftKey: true }), false)
})

test('workspace URL carries only explicit drill-down parameters', () => {
  assert.equal(workspaceUrl('operations',{intersection:'CR_01'}),'/operacional?intersection=CR_01')
  assert.equal(workspaceUrl('executive',{intersection:null}),'/executivo')
  assert.equal(workspaceUrl('missing',{}),'/executivo')
})
