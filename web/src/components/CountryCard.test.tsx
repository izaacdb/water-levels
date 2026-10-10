import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CurrentEntry, SourceInfo } from '../contract'
import { CountryCard } from './CountryCard'

const source: SourceInfo = {
  id: 'es-miteco',
  country: 'ES',
  name: 'MITECO',
  url: 'https://www.miteco.gob.es/',
}
const entry: CurrentEntry = {
  pct: 58.3,
  asOf: '2026-10-06',
  stale: false,
  nReporting: 375,
  nTotal: 402,
  normalPct: 43.6,
  anomalyPts: 14.7,
  normalYears: 10,
  flags: [],
}

describe('CountryCard', () => {
  it('shows % full, as-of date, coverage and a source link', () => {
    render(<CountryCard name="Spain" entry={entry} sources={[source]} />)
    expect(screen.getByText('58.3%')).toBeInTheDocument()
    expect(screen.getByText('+14.7 pts vs normal')).toBeInTheDocument()
    expect(screen.getByText(/6 Oct 2026/)).toBeInTheDocument()
    expect(screen.getByText(/375 of 402 reservoirs/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /MITECO/ })).toHaveAttribute('href', source.url)
    expect(screen.queryByText(/out of date/i)).not.toBeInTheDocument()
  })

  it('marks stale data as out of date', () => {
    render(<CountryCard name="Spain" entry={{ ...entry, stale: true }} sources={[source]} />)
    expect(screen.getByText(/out of date/i)).toBeInTheDocument()
  })
  it('explains a withdrawn country (E6)', () => {
    render(
      <CountryCard
        name="Spain"
        entry={{ ...entry, stale: true }}
        sources={[source]}
        status={{ code: 'ES', name: 'Spain', status: 'withdrawn', note: 'No longer meets the inclusion bar.' }}
      />,
    )
    expect(screen.getByText('Withdrawn')).toBeInTheDocument()
    expect(screen.getByText('No longer meets the inclusion bar.')).toBeInTheDocument()
  })

  it('links every source and shows a coverage note for a partly covered country (B1a, B2′)', () => {
    const yorkshire: SourceInfo = { id: 'uk-yorkshire', country: 'UK', name: 'Yorkshire Water', url: 'https://y/' }
    const severn: SourceInfo = { id: 'uk-severn-trent', country: 'UK', name: 'Severn Trent', url: 'https://s/', cadence: 'monthly' }
    render(
      <CountryCard
        name="United Kingdom"
        entry={entry}
        sources={[yorkshire, severn]}
        status={{ code: 'UK', name: 'United Kingdom', status: 'active', note: 'England only' }}
      />,
    )
    expect(screen.getByText(/Sources:/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Yorkshire Water' })).toHaveAttribute('href', 'https://y/')
    expect(screen.getByRole('link', { name: 'Severn Trent' })).toHaveAttribute('href', 'https://s/')
    expect(screen.getByText('England only')).toBeInTheDocument()
    expect(screen.getByText('(monthly)')).toBeInTheDocument()
    expect(screen.queryByText('Withdrawn')).not.toBeInTheDocument()
  })
})
