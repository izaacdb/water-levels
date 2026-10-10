import { describe, expect, it } from 'vitest'
import { DEFAULT_STATE, parseState, serializeState, validateState } from './urlState'

describe('url state', () => {
  it('defaults when the URL is empty', () => {
    expect(parseState('')).toEqual(DEFAULT_STATE)
  })

  it('round-trips every field (B22)', () => {
    const state = {
      mode: 'anom' as const,
      view: 'compare' as const,
      area: 'ES050',
      level: 'reservoir' as const,
      sort: 'anom' as const,
      dir: 'asc' as const,
      cmp: ['ES', 'PT', 'ES-albarellos'],
      at: { zoom: 5.5, lat: 40.1234, lon: -3.5 },
    }
    expect(parseState(serializeState(state))).toEqual(state)
  })

  it('omits defaults so links stay short', () => {
    expect(serializeState(DEFAULT_STATE)).toBe('')
    expect(serializeState({ ...DEFAULT_STATE, mode: 'anom' })).toBe('?mode=anom')
  })

  it('ignores junk values', () => {
    const s = parseState('?mode=rainbow&view=nope&dir=up&at=a/b/c&cmp=,,')
    expect(s).toEqual(DEFAULT_STATE)
  })

  it('caps the comparison at five areas and removes duplicates', () => {
    expect(parseState('?cmp=a,b,a,c,d,e,f').cmp).toEqual(['a', 'b', 'c', 'd', 'e'])
  })
})

describe('validateState (E7)', () => {
  it('drops ids that no longer exist and reports them', () => {
    const { state, missing } = validateState(
      { ...DEFAULT_STATE, area: 'ES-gone', cmp: ['ES', 'ES-old', 'PT'] },
      new Set(['ES', 'PT']),
    )
    expect(state.area).toBeNull()
    expect(state.cmp).toEqual(['ES', 'PT'])
    expect(missing).toEqual(['ES-gone', 'ES-old'])
  })
})
