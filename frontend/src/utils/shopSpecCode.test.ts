import { describe, it, expect } from 'vitest'

import {
  classifyShopSpecCode,
  isAutoMatchableShopSpecCode,
} from './shopSpecCode'

describe('classifyShopSpecCode', () => {
  it('classifies structured 3-char model codes as auto-matchable', () => {
    expect(classifyShopSpecCode('KB8').kind).toBe('structured')
    expect(classifyShopSpecCode('ozu').kind).toBe('structured')
    expect(classifyShopSpecCode('KB8').modelCode).toBe('KB8')
  })

  it('classifies XXX-YYY structured variant codes', () => {
    expect(classifyShopSpecCode('KB8-001').kind).toBe('structured')
    expect(classifyShopSpecCode('KB8-001').modelCode).toBe('KB8')
    expect(classifyShopSpecCode('KB8-001-TMALL').modelCode).toBe('KB8')
  })

  it('classifies pure-digit platform IDs as platform (NOT auto-matchable)', () => {
    expect(classifyShopSpecCode('986153092837').kind).toBe('platform')
    expect(classifyShopSpecCode('760985289146').kind).toBe('platform')
    expect(isAutoMatchableShopSpecCode('986153092837')).toBe(false)
  })

  it('rejects 3-digit-only as auto-matchable (collides with platform IDs)', () => {
    expect(classifyShopSpecCode('024').kind).toBe('platform')
  })

  it('classifies unstructured codes as malformed', () => {
    expect(classifyShopSpecCode('F26040205').kind).toBe('malformed')
    expect(classifyShopSpecCode('Q26010601C丝圈地垫').kind).toBe('malformed')
    expect(classifyShopSpecCode('Q25090802').kind).toBe('malformed')
  })

  it('classifies blanks as empty', () => {
    expect(classifyShopSpecCode(null).kind).toBe('empty')
    expect(classifyShopSpecCode(undefined).kind).toBe('empty')
    expect(classifyShopSpecCode('').kind).toBe('empty')
    expect(classifyShopSpecCode('   ').kind).toBe('empty')
  })

  it('preserves PM legacy prefix', () => {
    expect(classifyShopSpecCode('PM001').kind).toBe('structured')
    expect(classifyShopSpecCode('PM_OLD-A').kind).toBe('structured')
  })
})
