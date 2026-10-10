import { describe, expect, it } from 'vitest'
import type { Area, Series } from '../contract'
import { COMPARE_COLORS, assignSlots, compareOption } from './compare'

const area = (id: string, country = 'ES'): Area => ({ id, level: 'region', name: id, country, capacityHm3: 100, sourceIds: ['x'] })
const series = (id: string, pct: number[], normal: (number | null)[]): Series => ({
  areaId: id,
  weeks: ['2026-W40', '2026-W41'],
  pct,
  normal,
  p10: [null, null],
  p90: [null, null],
  n: [1, 1],
})

type S = { name: string; data: [number, number | null][]; lineStyle: { color: string }; endLabel: { show: boolean } }
const seriesOf = (o: unknown) => (o as { series: S[] }).series

describe('assignSlots', () => {
  it('keeps survivors on their colour when an area is removed', () => {
    const first = assignSlots(['a', 'b', 'c'], new Map())
    const after = assignSlots(['a', 'c'], first)
    expect(after.get('c')).toBe(first.get('c'))
    // A newcomer takes the freed slot.
    expect(assignSlots(['a', 'c', 'd'], after).get('d')).toBe(first.get('b'))
  })
})

describe('compareOption', () => {
  const items = [
    { area: area('A'), series: series('A', [40, 50], [30, 30]), slot: 0 },
    { area: area('B', 'PT'), series: series('B', [60, 62], [null, null]), slot: 1 },
  ]

  it('draws one labelled line per area in its slot colour (B20)', () => {
    const s = seriesOf(compareOption(items, 'pct'))
    expect(s.map((x) => x.name)).toEqual(['A', 'B'])
    expect(s.map((x) => x.lineStyle.color)).toEqual([COMPARE_COLORS[0], COMPARE_COLORS[1]])
    expect(s[0].data.map((d) => d[1])).toEqual([40, 50])
    expect(s.every((x) => x.endLabel.show)).toBe(true)
  })

  it('plots vs normal as % full minus normal, with gaps where there is no normal', () => {
    const s = seriesOf(compareOption(items, 'anom'))
    expect(s[0].data.map((d) => d[1])).toEqual([10, 20])
    expect(s[1].data.map((d) => d[1])).toEqual([null, null])
  })
})
