import { describe, expect, it } from 'vitest'
import type { Area, CurrentEntry } from '../contract'
import { tooltipLines } from './tooltip'

const area: Area = { id: 'ES050', level: 'region', name: 'Guadalquivir', country: 'ES', capacityHm3: 8000, sourceIds: ['es-miteco'] }
const entry: CurrentEntry = {
  pct: 69.1,
  anomalyPts: 35.7,
  normalPct: 33.4,
  normalYears: 10,
  asOf: '2026-10-06',
  stale: false,
  nReporting: 38,
  nTotal: 41,
  flags: [],
}

describe('tooltipLines', () => {
  it('has name with country, % full, vs normal, as-of date and coverage', () => {
    expect(tooltipLines(area, entry)).toEqual({
      title: 'Guadalquivir',
      subtitle: 'River basin · Spain',
      lines: ['69.1% full', '+35.7 pts vs normal', 'As of 6 Oct 2026', '38 of 41 reservoirs reporting'],
      stale: false,
    })
  })

  it('calls a published total what it is rather than counting reservoirs (B25)', () => {
    const t = tooltipLines({ ...area, totalOnly: true }, { ...entry, nReporting: 1, nTotal: 1 })
    expect(t.lines).toContain('Published total, not per reservoir')
    expect(t.lines.join(' ')).not.toMatch(/reservoirs reporting/)
  })

  it('says insufficient history when there is no normal (E2)', () => {
    const t = tooltipLines(area, { ...entry, anomalyPts: null, normalPct: null, normalYears: 2 })
    expect(t.lines[1]).toBe('vs normal: insufficient history')
  })

  it('labels a normal built on fewer than 10 years (B7)', () => {
    const t = tooltipLines(area, { ...entry, anomalyPts: -4.25, normalYears: 6 })
    expect(t.lines[1]).toBe('−4.3 pts vs normal (based on 6 years)')
  })

  it('omits the coverage line for a single reservoir', () => {
    const t = tooltipLines({ ...area, level: 'reservoir', name: 'Albarellos' }, { ...entry, nReporting: 1, nTotal: 1 })
    expect(t.subtitle).toBe('Reservoir · Spain')
    expect(t.lines).not.toContain('1 of 1 reservoirs reporting')
  })
  it('notes a reading shown as published but outside capacity (E4)', () => {
    const t = tooltipLines({ ...area, level: 'reservoir' }, { ...entry, pct: 160, flags: ['over_capacity'] })
    expect(t.lines).toContain('Reported value exceeds capacity')
  })
})
