import { describe, expect, it } from 'vitest'
import { NOT_COVERED, PCT_BINS, pctColor } from './scale'

describe('pctColor', () => {
  it('bins % full into a light-to-dark single-hue ramp', () => {
    const colors = [5, 25, 45, 65, 85].map(pctColor)
    expect(new Set(colors).size).toBe(5)
    expect(colors).toEqual(PCT_BINS.map((b) => b.color))
  })

  it('puts boundaries in the upper bin and clamps out-of-range values', () => {
    expect(pctColor(20)).toBe(PCT_BINS[1].color)
    expect(pctColor(100)).toBe(PCT_BINS[4].color)
    expect(pctColor(120)).toBe(PCT_BINS[4].color)
    expect(pctColor(-3)).toBe(PCT_BINS[0].color)
  })

  it('has a distinct neutral for countries without data', () => {
    expect(PCT_BINS.map((b) => b.color)).not.toContain(NOT_COVERED)
  })
})
