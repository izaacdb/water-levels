import type { Series } from '../contract'
import { formatDate } from './format'
import { isoWeekParts, isoWeekStart } from './week'

// Chart ink (light surface) — see the dataviz reference palette.
export const INK = {
  primary: '#0b0b0b',
  secondary: '#52514e',
  muted: '#898781',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  series: '#2a78d6',
  band: '#cde2fb',
  normal: '#52514e',
  pastYear: '#c3c2b7',
}

const axisCommon = {
  axisLine: { lineStyle: { color: INK.axis } },
  axisTick: { show: false },
  axisLabel: { color: INK.muted, fontSize: 11 },
  splitLine: { lineStyle: { color: INK.grid } },
}

const pctAxis = {
  ...axisCommon,
  type: 'value' as const,
  min: 0,
  max: 100,
  interval: 25,
  axisLabel: { ...axisCommon.axisLabel, formatter: '{value}%' },
}

const hasNumber = (v: number | null): v is number => v != null

/** B17: % full over the 10-year window, with the normal band behind it. */
export function trendOption(s: Series) {
  const t = s.weeks.map((w) => isoWeekStart(w).getTime())
  const hasBand = s.p10.some(hasNumber) && s.p90.some(hasNumber)
  const band = hasBand
    ? [
        {
          name: 'p10',
          type: 'line' as const,
          stack: 'band',
          data: t.map((x, i) => [x, s.p10[i]]),
          lineStyle: { opacity: 0 },
          symbol: 'none',
          silent: true,
          tooltip: { show: false },
        },
        {
          name: 'Normal range (10th–90th percentile)',
          type: 'line' as const,
          stack: 'band',
          data: t.map((x, i) => [x, hasNumber(s.p90[i]) && hasNumber(s.p10[i]) ? s.p90[i]! - s.p10[i]! : null]),
          lineStyle: { opacity: 0 },
          areaStyle: { color: INK.band, opacity: 0.8 },
          symbol: 'none',
          silent: true,
        },
        {
          name: 'Normal',
          type: 'line' as const,
          data: t.map((x, i) => [x, s.normal[i]]),
          lineStyle: { color: INK.normal, width: 1, type: 'dashed' as const },
          itemStyle: { color: INK.normal },
          symbol: 'none',
        },
      ]
    : []
  return {
    animation: false,
    grid: { left: 40, right: 12, top: 12, bottom: 28 },
    xAxis: { ...axisCommon, type: 'time' as const, splitLine: { show: false } },
    yAxis: pctAxis,
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'line' as const, lineStyle: { color: INK.axis } },
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0
        const date = formatDate(isoWeekStart(s.weeks[i]).toISOString().slice(0, 10))
        const normal = s.normal[i] == null ? '' : `<br/>Normal ${s.normal[i]?.toFixed(1)}%`
        return `<strong>Week of ${date}</strong><br/>${s.pct[i].toFixed(1)}% full${normal}`
      },
    },
    series: [
      ...band,
      {
        name: '% full',
        type: 'line' as const,
        data: t.map((x, i) => [x, s.pct[i]]),
        lineStyle: { color: INK.series, width: 2 },
        itemStyle: { color: INK.series },
        symbol: 'none',
      },
    ],
  }
}

/** B18: each year on a Jan–Dec (ISO week) axis, current year highlighted. */
export function yearOnYearOption(s: Series) {
  const byYear = new Map<number, [number, number][]>()
  s.weeks.forEach((w, i) => {
    const { year, week } = isoWeekParts(w)
    if (!byYear.has(year)) byYear.set(year, [])
    byYear.get(year)!.push([week, s.pct[i]])
  })
  const years = [...byYear.keys()].sort()
  const latest = years[years.length - 1]
  return {
    animation: false,
    grid: { left: 40, right: 44, top: 12, bottom: 28 },
    xAxis: {
      ...axisCommon,
      type: 'value' as const,
      min: 1,
      max: 53,
      interval: 13,
      splitLine: { show: false },
      axisLabel: {
        ...axisCommon.axisLabel,
        formatter: (week: number) => ({ 1: 'Jan', 14: 'Apr', 27: 'Jul', 40: 'Oct' })[week] ?? '',
      },
    },
    yAxis: pctAxis,
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'line' as const, lineStyle: { color: INK.axis } },
      valueFormatter: (v: number) => `${v.toFixed(1)}%`,
    },
    series: years.map((year) => {
      const current = year === latest
      return {
        name: String(year),
        type: 'line' as const,
        data: byYear.get(year)!,
        z: current ? 3 : 2,
        lineStyle: { color: current ? INK.series : INK.pastYear, width: current ? 2.5 : 1 },
        itemStyle: { color: current ? INK.series : INK.pastYear },
        symbol: 'none',
        // Direct label on the highlighted line only (selective labelling).
        endLabel: current ? { show: true, formatter: String(year), color: INK.primary, fontWeight: 600 } : undefined,
      }
    }),
  }
}
