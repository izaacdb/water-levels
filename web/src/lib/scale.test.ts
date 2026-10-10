import { describe, expect, it } from 'vitest'
import type { CurrentEntry } from '../contract'
import { ANOM_BINS, INSUFFICIENT, NOT_COVERED, PCT_BINS, anomalyColor, colorFor, pctColor } from './scale'

const entry = (over: Partial<CurrentEntry> = {}): CurrentEntry => ({
  pct: 50,
  asOf: '2026-10-06',
  stale: false,
  nReporting: 1,
  nTotal: 1,
  normalYears: 10,
  anomalyPts: 0,
  normalPct: 50,
  flags: [],
  ...over,
})

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
})

describe('anomalyColor', () => {
  it('is diverging: drier than normal one hue, wetter another, neutral near zero', () => {
    const neutral = anomalyColor(0)
    expect(anomalyColor(-2.9)).toBe(neutral)
    expect(anomalyColor(2.9)).toBe(neutral)
    expect(anomalyColor(-25)).toBe(ANOM_BINS[0].color)
    expect(anomalyColor(25)).toBe(ANOM_BINS[ANOM_BINS.length - 1].color)
    expect(anomalyColor(-15)).not.toBe(anomalyColor(15))
  })
})

describe('colorFor', () => {
  it('uses the mode to pick the encoding', () => {
    expect(colorFor(entry({ pct: 85 }), 'pct')).toBe(pctColor(85))
    expect(colorFor(entry({ anomalyPts: -25 }), 'anom')).toBe(anomalyColor(-25))
  })

  it('shows insufficient history as its own neutral in vs-normal mode (E2)', () => {
    expect(colorFor(entry({ anomalyPts: null, normalYears: 3 }), 'anom')).toBe(INSUFFICIENT)
  })

  it('shows no data as not covered', () => {
    expect(colorFor(undefined, 'pct')).toBe(NOT_COVERED)
    expect(new Set([NOT_COVERED, INSUFFICIENT, ...ANOM_BINS.map((b) => b.color)]).size).toBe(ANOM_BINS.length + 2)
  })
})
