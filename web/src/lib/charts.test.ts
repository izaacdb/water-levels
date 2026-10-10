import { describe, expect, it } from 'vitest'
import type { Series } from '../contract'
import { trendOption, yearOnYearOption } from './charts'

const series: Series = {
  areaId: 'ES',
  weeks: ['2025-W40', '2025-W41', '2026-W40', '2026-W41'],
  pct: [30, 31, 55, 58.3],
  normal: [40, 41, 42, 43.6],
  p10: [20, 21, 22, 23],
  p90: [60, 61, 62, 63],
  n: [375, 375, 375, 375],
}

type AnySeries = { name?: string; data: unknown[]; stack?: string; lineStyle?: { width?: number; color?: string } }
const seriesOf = (opt: unknown) => (opt as { series: AnySeries[] }).series

describe('trendOption', () => {
  it('draws the band as a stacked p10 base plus the p90-p10 width, then normal, then % full', () => {
    const s = seriesOf(trendOption(series))
    const band = s.filter((x) => x.stack === 'band')
    expect(band.map((x) => x.data.map((d) => (d as [number, number])[1]))).toEqual([
      [20, 21, 22, 23],
      [40, 40, 40, 40],
    ])
    expect(s.map((x) => x.name)).toEqual(['p10', 'Normal range (10th–90th percentile)', 'Normal', '% full'])
  })

  it('omits the band and normal when there is no history (E2)', () => {
    const none = { ...series, normal: series.normal.map(() => null), p10: series.p10.map(() => null), p90: series.p90.map(() => null) }
    expect(seriesOf(trendOption(none)).map((x) => x.name)).toEqual(['% full'])
  })
})

describe('yearOnYearOption', () => {
  it('has one line per year on a week-of-year axis, the current year emphasised', () => {
    const s = seriesOf(yearOnYearOption(series))
    expect(s.map((x) => x.name)).toEqual(['2025', '2026'])
    expect(s[1].data).toContainEqual([41, 58.3])
    expect(s[1].lineStyle?.width).toBeGreaterThan(s[0].lineStyle?.width ?? 0)
  })
})
