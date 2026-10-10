// Lazily loaded: ECharts is only fetched when someone opens an area.
import { LineChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import type { Series } from '../contract'
import { trendOption, yearOnYearOption } from '../lib/charts'
import { type CompareItem, compareOption } from '../lib/compare'
import type { Mode } from '../lib/scale'

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

function EChart({ option, label }: { option: EChartsCoreOption; label: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(option)
    const resize = new ResizeObserver(() => chart.resize())
    resize.observe(ref.current)
    return () => {
      resize.disconnect()
      chart.dispose()
    }
  }, [option])
  return <div ref={ref} className="chart" role="img" aria-label={label} />
}

export function TrendChart({ series }: { series: Series }) {
  return <EChart option={trendOption(series) as EChartsCoreOption} label="Weekly % full over the last 10 years, with the normal range" />
}

export function YearOnYearChart({ series }: { series: Series }) {
  return <EChart option={yearOnYearOption(series) as EChartsCoreOption} label="% full by week of year, one line per year" />
}

export function CompareChart({ items, mode }: { items: CompareItem[]; mode: Mode }) {
  return (
    <EChart
      option={compareOption(items, mode) as EChartsCoreOption}
      label={`Comparison of ${items.map((i) => i.area.name).join(', ')}`}
    />
  )
}
