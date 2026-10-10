import { describe, expect, it } from 'vitest'
import type { Area, Current, CurrentEntry } from '../contract'
import { rankAreas } from './rankings'

const area = (id: string, level: Area['level'] = 'region'): Area => ({
  id,
  level,
  name: id,
  country: 'ES',
  capacityHm3: 100,
  sourceId: 'es-miteco',
})
const entry = (pct: number, anomalyPts: number | null, stale = false): CurrentEntry => ({
  pct,
  anomalyPts,
  normalYears: anomalyPts == null ? 2 : 10,
  asOf: '2026-10-06',
  stale,
  nReporting: 1,
  nTotal: 1,
  flags: [],
})

const areas = [area('A'), area('B'), area('C'), area('D'), area('E'), area('ES', 'country')]
const current: Current = {
  A: entry(40, -5),
  B: entry(80, 10),
  C: entry(60, null),
  D: entry(20, -30, true),
  E: entry(70, 2),
  ES: entry(55, 3),
}

describe('rankAreas', () => {
  it('ranks only the chosen level, by % full descending', () => {
    const r = rankAreas(areas, current, { level: 'region', sort: 'pct', dir: 'desc' })
    expect(r.ranked.map((a) => a.area.id)).toEqual(['B', 'E', 'C', 'A'])
  })

  it('sorts by vs normal ascending and leaves out insufficient history (E2)', () => {
    const r = rankAreas(areas, current, { level: 'region', sort: 'anom', dir: 'asc' })
    expect(r.ranked.map((a) => a.area.id)).toEqual(['A', 'E', 'B'])
    expect(r.unranked.map((a) => a.area.id)).toEqual(['C'])
  })

  it('lists stale areas separately as awaiting update (B15)', () => {
    const r = rankAreas(areas, current, { level: 'region', sort: 'pct', dir: 'desc' })
    expect(r.awaiting.map((a) => a.area.id)).toEqual(['D'])
    expect(r.ranked.map((a) => a.area.id)).not.toContain('D')
  })
})
