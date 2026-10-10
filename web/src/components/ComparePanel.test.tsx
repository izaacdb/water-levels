import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { Area, Current } from '../contract'
import { ComparePanel } from './ComparePanel'

vi.mock('./LazyCharts', () => ({ CompareChart: () => <div data-testid="compare-chart" /> }))
vi.mock('../lib/data', async (orig) => ({
  ...(await orig<typeof import('../lib/data')>()),
  loadSeries: (id: string) =>
    Promise.resolve({ areaId: id, weeks: ['2026-W41'], pct: [50], normal: [40], p10: [30], p90: [60], n: [1] }),
}))

const mk = (id: string, name: string, level: Area['level'] = 'region', country = 'ES'): Area => ({
  id,
  level,
  name,
  country,
  capacityHm3: 1234,
  sourceId: 'x',
})
const areas = [mk('ES', 'Spain', 'country'), mk('ES050', 'Guadalquivir'), mk('ES091', 'Ebro'), mk('ES030', 'Tajo'), mk('ES020', 'Duero'), mk('ES040', 'Guadiana'), mk('ES010', 'Miño-Sil')]
const current: Current = Object.fromEntries(
  areas.map((a) => [a.id, { pct: 50, normalYears: 10, asOf: '2026-10-06', stale: false, nReporting: 1, nTotal: 1, flags: [] }]),
)

function Harness({ initial = [] as string[] }) {
  const [ids, setIds] = useState(initial)
  return <ComparePanel areas={areas} current={current} ids={ids} mode="pct" onModeChange={() => {}} onChange={setIds} onSelect={() => {}} />
}

describe('ComparePanel', () => {
  it('asks for at least two areas', () => {
    render(<Harness initial={['ES']} />)
    expect(screen.getByText(/add at least one more area/i)).toBeInTheDocument()
    expect(screen.queryByTestId('compare-chart')).not.toBeInTheDocument()
  })

  it('adds areas found by name, from any level (B19, B21)', async () => {
    render(<Harness initial={['ES']} />)
    fireEvent.change(screen.getByLabelText(/add an area/i), { target: { value: 'guadal' } })
    fireEvent.click(screen.getByRole('button', { name: /Guadalquivir/ }))
    expect(screen.getByRole('listitem', { name: /Guadalquivir/ })).toBeInTheDocument()
    expect(await screen.findByTestId('compare-chart')).toBeInTheDocument()
  })

  it('removes areas', () => {
    render(<Harness initial={['ES', 'ES050']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove Guadalquivir' }))
    expect(screen.queryByRole('listitem', { name: /Guadalquivir/ })).not.toBeInTheDocument()
  })

  it('stops at five areas', () => {
    render(<Harness initial={['ES', 'ES050', 'ES091', 'ES030', 'ES020']} />)
    expect(screen.getByLabelText(/add an area/i)).toBeDisabled()
    expect(screen.getByText(/up to 5 areas/i)).toBeInTheDocument()
  })

  it('shows capacity and country in the legend (E8)', () => {
    render(<Harness initial={['ES', 'ES050']} />)
    expect(screen.getByRole('listitem', { name: /Guadalquivir/ })).toHaveTextContent('Spain · 1,234 hm³')
  })
})
