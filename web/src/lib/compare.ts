import type { Area, Series } from '../contract'
import { INK } from './charts'
import { formatDate } from './format'
import type { Mode } from './scale'
import { isoWeekStart } from './week'

// Categorical slots in fixed order (dataviz reference palette); never cycled.
export const COMPARE_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4'] as const

/** Colour follows the entity: survivors keep their slot, newcomers take the lowest free one. */
export function assignSlots(ids: string[], previous: Map<string, number>): Map<string, number> {
  const next = new Map<string, number>()
  for (const id of ids) if (previous.has(id)) next.set(id, previous.get(id)!)
  const used = new Set(next.values())
  for (const id of ids) {
    if (next.has(id)) continue
    let slot = 0
    while (used.has(slot)) slot++
    next.set(id, slot)
    used.add(slot)
  }
  return next
}

export interface CompareItem {
  area: Area
  series: Series
  slot: number
}

/** B20: one line per area, as % full or vs normal. */
export function compareOption(items: CompareItem[], mode: Mode) {
  const value = (s: Series, i: number) =>
    mode === 'pct' ? s.pct[i] : s.normal[i] == null ? null : Math.round((s.pct[i] - s.normal[i]!) * 10) / 10
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 12, bottom: 28 },
    xAxis: {
      type: 'time' as const,
      axisLine: { lineStyle: { color: INK.axis } },
      axisTick: { show: false },
      axisLabel: { color: INK.muted, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value' as const,
      ...(mode === 'pct' ? { min: 0, max: 100, interval: 25 } : {}),
      axisLine: { show: false },
      axisLabel: { color: INK.muted, fontSize: 11, formatter: mode === 'pct' ? '{value}%' : '{value} pts' },
      splitLine: { lineStyle: { color: INK.grid } },
    },
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'line' as const, lineStyle: { color: INK.axis } },
      formatter: (params: { seriesName: string; value: [number, number | null]; color: string }[]) => {
        if (!params.length) return ''
        const date = formatDate(new Date(params[0].value[0]).toISOString().slice(0, 10))
        const rows = params.map((p) => {
          const v = p.value[1]
          const shown = v == null ? '—' : mode === 'pct' ? `${v.toFixed(1)}%` : `${v > 0 ? '+' : ''}${v.toFixed(1)} pts`
          return `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${p.color};margin-right:6px"></span>${p.seriesName}: <strong>${shown}</strong>`
        })
        return [`<strong>Week of ${date}</strong>`, ...rows].join('<br/>')
      },
    },
    series: items.map(({ area, series, slot }) => ({
      name: area.name,
      type: 'line' as const,
      data: series.weeks.map((w, i) => [isoWeekStart(w).getTime(), value(series, i)] as [number, number | null]),
      lineStyle: { color: COMPARE_COLORS[slot], width: 2 },
      itemStyle: { color: COMPARE_COLORS[slot] },
      symbol: 'none',
      connectNulls: false,
      ...(mode === 'anom'
        ? { markLine: { silent: true, symbol: 'none', label: { show: false }, data: [{ yAxis: 0 }], lineStyle: { color: INK.axis, type: 'solid' as const } } }
        : {}),
    })),
  }
}
