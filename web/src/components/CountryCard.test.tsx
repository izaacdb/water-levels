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
  flags: [],
}

describe('CountryCard', () => {
  it('shows % full, as-of date, coverage and a source link', () => {
    render(<CountryCard name="Spain" entry={entry} source={source} />)
    expect(screen.getByText('58.3%')).toBeInTheDocument()
    expect(screen.getByText(/6 Oct 2026/)).toBeInTheDocument()
    expect(screen.getByText(/375 of 402 reservoirs/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /MITECO/ })).toHaveAttribute('href', source.url)
    expect(screen.queryByText(/out of date/i)).not.toBeInTheDocument()
  })

  it('marks stale data as out of date', () => {
    render(<CountryCard name="Spain" entry={{ ...entry, stale: true }} source={source} />)
    expect(screen.getByText(/out of date/i)).toBeInTheDocument()
  })
})
