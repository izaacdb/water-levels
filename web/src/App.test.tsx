import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./components/MapView', () => ({ MapView: () => <div data-testid="map" /> }))

const payloads: Record<string, unknown> = {
  'data/manifest.json': {
    schemaVersion: 1,
    generatedAt: '2026-10-10T06:00:00Z',
    snapshotWeek: '2026-W41',
    countries: [{ code: 'ES', name: 'Spain', status: 'active' }],
    sources: [{ id: 'es-miteco', country: 'ES', name: 'MITECO', url: 'https://www.miteco.gob.es/' }],
  },
  'data/areas.json': [{ id: 'ES', level: 'country', name: 'Spain', country: 'ES', capacityHm3: 56000, sourceId: 'es-miteco' }],
  'data/current.json': {
    ES: { pct: 58.3, asOf: '2026-10-06', stale: false, nReporting: 375, nTotal: 402, flags: [] },
  },
}

afterEach(() => vi.unstubAllGlobals())

describe('App', () => {
  it('shows the snapshot week, the map and a card per covered country', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const key = Object.keys(payloads).find((k) => url.endsWith(k))
        return new Response(JSON.stringify(key ? payloads[key] : null), { status: key ? 200 : 404 })
      }),
    )
    render(<App />)
    expect(await screen.findByText('Week 41, 2026')).toBeInTheDocument()
    expect(screen.getByTestId('map')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Spain' })).toBeInTheDocument()
    expect(screen.getByText(/not covered/i, { selector: 'p' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Rankings' }))
    expect(screen.getByLabelText('Sort by')).toBeInTheDocument()
  })

  it('reports a load failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 500 })))
    render(<App />)
    expect(await screen.findByText(/couldn't load data/i)).toBeInTheDocument()
  })
})
