import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Area, CurrentEntry, SourceInfo } from '../contract'
import { AreaDetail } from './AreaDetail'

vi.mock('./LazyCharts', () => ({
  TrendChart: () => <div data-testid="trend" />,
  YearOnYearChart: () => <div data-testid="yoy" />,
}))
vi.mock('../lib/data', async (orig) => ({
  ...(await orig<typeof import('../lib/data')>()),
  useSeries: () => ({ status: 'ready', data: { areaId: 'ES050', weeks: [], pct: [], normal: [], p10: [], p90: [], n: [] } }),
}))

const area: Area = { id: 'ES050', level: 'region', name: 'Guadalquivir', country: 'ES', parentId: 'ES', capacityHm3: 8113.4, sourceId: 'es-miteco' }
const parent: Area = { id: 'ES', level: 'country', name: 'Spain', country: 'ES', capacityHm3: 56000, sourceId: 'es-miteco' }
const entry: CurrentEntry = { pct: 69.1, anomalyPts: 35.7, normalPct: 33.4, normalYears: 10, asOf: '2026-10-06', stale: false, nReporting: 47, nTotal: 47, flags: [] }
const source: SourceInfo = { id: 'es-miteco', country: 'ES', name: 'MITECO', url: 'https://www.miteco.gob.es/' }

describe('AreaDetail', () => {
  it('shows the figures, source and both charts (B16–B18)', async () => {
    render(<AreaDetail area={area} entry={entry} source={source} parent={parent} onBack={() => {}} onSelect={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Guadalquivir' })).toBeInTheDocument()
    expect(screen.getByText('69.1%')).toBeInTheDocument()
    expect(screen.getByText('+35.7 pts vs normal')).toBeInTheDocument()
    expect(screen.getByText(/8,113 hm³/)).toBeInTheDocument()
    expect(screen.getByText(/6 Oct 2026/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'MITECO' })).toHaveAttribute('href', source.url)
    expect(await screen.findByTestId('trend')).toBeInTheDocument()
    expect(await screen.findByTestId('yoy')).toBeInTheDocument()
  })

  it('navigates back and up to the parent area', () => {
    const onBack = vi.fn()
    const onSelect = vi.fn()
    render(<AreaDetail area={area} entry={entry} source={source} parent={parent} onBack={onBack} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(onBack).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Spain' }))
    expect(onSelect).toHaveBeenCalledWith('ES')
  })
})
