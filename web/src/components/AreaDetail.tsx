import { Suspense } from 'react'
import type { Area, CurrentEntry, SourceInfo } from '../contract'
import { useSeries } from '../lib/data'
import { TOTAL_ONLY_NOTE, countryName, formatDate, formatPct, sourceLabel } from '../lib/format'
import { pctColor } from '../lib/scale'
import { flagNotes, normalLine } from '../lib/tooltip'
import { TrendChart, YearOnYearChart } from './LazyCharts'
import { SourceLinks } from './SourceLinks'


const LEVEL = { country: 'Country', region: 'River basin district', reservoir: 'Reservoir' } as const
const hm3 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })

interface Props {
  area: Area
  entry: CurrentEntry
  sources: SourceInfo[]
  parent?: Area
  onBack: () => void
  onSelect: (id: string) => void
  /** Absent when the area is already in the comparison or it's full. */
  onCompare?: () => void
  /** Why this area's country is stale or withdrawn (E5/E6). */
  countryNote?: string
}

export function AreaDetail({ area, entry, sources, parent, onBack, onSelect, onCompare, countryNote }: Props) {
  const series = useSeries(area.id)
  return (
    <section className="detail" aria-labelledby="detail-title">
      <button type="button" className="link-button" onClick={onBack}>
        ← Back
      </button>
      <header className="card-head">
        <span className="swatch" style={{ background: pctColor(entry.pct) }} aria-hidden />
        <h2 id="detail-title">{area.name}</h2>
        {entry.stale && <span className="stale">Out of date</span>}
      </header>
      <p className="meta">
        {LEVEL[area.level]}
        {area.level !== 'country' && <> · {countryName(area.country)}</>}
        {parent && parent.level === 'region' && (
          <>
            {' '}
            · in{' '}
            <button type="button" className="link-button" onClick={() => onSelect(parent.id)}>
              {parent.name}
            </button>
          </>
        )}
        {parent && parent.level === 'country' && (
          <>
            {' '}
            · part of{' '}
            <button type="button" className="link-button" onClick={() => onSelect(parent.id)}>
              {parent.name}
            </button>
          </>
        )}
      </p>
      <p className="hero">
        {formatPct(entry.pct)} <span className="hero-label">full</span>
      </p>
      <p className="normal">{normalLine(entry)}</p>
      {countryNote && <p className="status-note">{countryNote}</p>}
      {area.totalOnly && <p className="status-note">{TOTAL_ONLY_NOTE}</p>}
      {flagNotes(entry).map((note) => (
        <p key={note} className="notice">
          {note}. Shown as published; left out of basin and country totals.
        </p>
      ))}
      <dl className="facts">
        {!area.totalOnly && (
          <>
            <dt>Capacity</dt>
            <dd>{hm3.format(area.capacityHm3)} hm³</dd>
          </>
        )}
        <dt>As of</dt>
        <dd>{formatDate(entry.asOf)}</dd>
        {area.level !== 'reservoir' && !area.totalOnly && (
          <>
            <dt>Reporting</dt>
            <dd>
              {entry.nReporting} of {entry.nTotal} reservoirs
            </dd>
          </>
        )}
        {sources.length > 0 && (
          <>
            <dt>{sourceLabel(sources)}</dt>
            <dd>
              <SourceLinks sources={sources} />
            </dd>
          </>
        )}
      </dl>

      {onCompare && (
        <button type="button" className="secondary-button" onClick={onCompare}>
          + Add to comparison
        </button>
      )}

      <h3>Last 10 years</h3>
      {series.status === 'ready' ? (
        <Suspense fallback={<div className="chart chart-loading">Loading chart…</div>}>
          <TrendChart series={series.data} />
          <p className="chart-note">
            Shaded: the normal range for each week (10th–90th percentile of the previous 10 years). Dashed: the
            average.
          </p>
          <h3>Year on year</h3>
          <YearOnYearChart series={series.data} />
        </Suspense>
      ) : series.status === 'error' ? (
        <p className="status error">Couldn't load history.</p>
      ) : (
        <div className="chart chart-loading">Loading history…</div>
      )}
    </section>
  )
}
