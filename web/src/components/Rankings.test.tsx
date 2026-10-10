import { fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { Area, Current } from '../contract'
import type { RankOptions } from '../lib/rankings'
import { Rankings } from './Rankings'

function Harness({ onSelect = () => {} }: { onSelect?: (id: string) => void }) {
  const [opts, setOpts] = useState<RankOptions>({ level: 'country', sort: 'pct', dir: 'desc' })
  return <Rankings areas={areas} current={current} opts={opts} onChange={setOpts} onSelect={onSelect} />
}

const mk = (id: string, name: string): Area => ({ id, level: 'region', name, country: 'ES', parentId: 'ES', capacityHm3: 1, sourceId: 'x' })
const areas = [mk('A', 'Ebro'), mk('B', 'Tajo'), mk('C', 'Segura')]
const base = { normalYears: 10, asOf: '2026-10-06', nReporting: 1, nTotal: 1, flags: [] }
const current: Current = {
  A: { ...base, pct: 45, anomalyPts: -3, stale: false },
  B: { ...base, pct: 54, anomalyPts: 8, stale: false },
  C: { ...base, pct: 49, anomalyPts: 1, stale: true },
}

const names = () => within(screen.getByRole('list', { name: /ranked/i })).getAllByRole('button').map((b) => b.querySelector('.rank-name')?.textContent)

describe('Rankings', () => {
  it('lists the chosen level fullest first, with stale areas set apart', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Level'), { target: { value: 'region' } })
    expect(names()).toEqual(['Tajo', 'Ebro'])
    expect(within(screen.getByRole('list', { name: /awaiting update/i })).getByText('Segura')).toBeInTheDocument()
  })

  it('re-sorts by vs normal and reverses direction', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('Level'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'anom' } })
    fireEvent.click(screen.getByRole('button', { name: /highest first/i }))
    expect(names()).toEqual(['Ebro', 'Tajo'])
  })

  it('selects an area', () => {
    const onSelect = vi.fn()
    render(<Harness onSelect={onSelect} />)
    fireEvent.change(screen.getByLabelText('Level'), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /Tajo/ }))
    expect(onSelect).toHaveBeenCalledWith('B')
  })
})
