import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useUrlState } from './useUrlState'

afterEach(() => window.history.replaceState(null, '', '/'))

describe('useUrlState', () => {
  it('reads the initial state from the URL', () => {
    window.history.replaceState(null, '', '/?mode=anom&cmp=ES,PT')
    const { result } = renderHook(() => useUrlState())
    expect(result.current[0].mode).toBe('anom')
    expect(result.current[0].cmp).toEqual(['ES', 'PT'])
  })

  it('writes updates back to the URL', () => {
    const { result } = renderHook(() => useUrlState())
    act(() => result.current[1]({ view: 'rankings', level: 'reservoir' }))
    expect(result.current[0].view).toBe('rankings')
    expect(window.location.search).toBe('?view=rankings&level=reservoir')
  })
})
