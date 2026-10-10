import { lazy } from 'react'

// ECharts is code-split: it only loads when someone opens an area.
export const TrendChart = lazy(() => import('./Charts').then((m) => ({ default: m.TrendChart })))
export const YearOnYearChart = lazy(() => import('./Charts').then((m) => ({ default: m.YearOnYearChart })))
export const CompareChart = lazy(() => import('./Charts').then((m) => ({ default: m.CompareChart })))
