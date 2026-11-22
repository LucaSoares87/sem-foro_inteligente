import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchHealth, displayStatus, websocketUrl } from '../src/health.js'

test('uses same origin and secure WebSocket when HTTPS', () => {
  assert.equal(websocketUrl({protocol:'https:',host:'demo.example'}), 'wss://demo.example/api/v1/ws/realtime')
  assert.equal(websocketUrl({protocol:'http:',host:'localhost:5173'}), 'ws://localhost:5173/api/v1/ws/realtime')
})
test('unimplemented never appears online', () => {
  assert.equal(displayStatus('not_implemented'), 'Não implementado')
  assert.equal(displayStatus('invented'), 'Desconhecido')
})
test('readiness 503 remains visible', async () => {
  const data = await fetchHealth(undefined, async () => ({status:503,json:async()=>({status:'degraded'})}))
  assert.equal(data.status, 'degraded')
})
test('rejects inconsistent transport or payload', async () => {
  await assert.rejects(fetchHealth(undefined, async()=>({status:500})))
  await assert.rejects(fetchHealth(undefined, async()=>({status:200,json:async()=>({status:'degraded'})})))
})
