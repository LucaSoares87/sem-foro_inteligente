import test from 'node:test'
import assert from 'node:assert/strict'
import {nextPresentationStep,presentationSteps,previousPresentationStep} from '../src/app/presentation.js'

test('guided presentation is finite, ordered and marks synthetic content',()=>{
  assert.deepEqual(presentationSteps.map(step=>step.id),['overview','intersection','history','intelligence','simulation','evidence','readiness'])
  assert.equal(presentationSteps.filter(step=>step.kind==='synthetic').length,2)
  assert.equal(presentationSteps.at(-1).id,'readiness')
})

test('presentation navigation wraps without invalid indices',()=>{
  assert.equal(nextPresentationStep(0),1)
  assert.equal(nextPresentationStep(presentationSteps.length-1),0)
  assert.equal(previousPresentationStep(0),presentationSteps.length-1)
  assert.equal(previousPresentationStep(2),1)
  assert.equal(nextPresentationStep(-1),0)
})
