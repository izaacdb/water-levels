import type { CountryStatus, CurrentEntry, SourceInfo } from '../contract'
import { formatDate, formatPct } from '../lib/format'
import { pctColor } from '../lib/scale'
import { normalLine } from '../lib/tooltip'

interface Props {
  name: string
  entry: CurrentEntry
  source: SourceInfo
  status?: CountryStatus
}

export function CountryCard({ name, entry, source, status }: Props) {
  const withdrawn = status?.status === 'withdrawn'
  return (
    <article className="card">
      <header className="card-head">
        <span className="swatch" style={{ background: pctColor(entry.pct) }} aria-hidden />
        <h2>{name}</h2>
        {withdrawn ? (
          <span className="stale">Withdrawn</span>
        ) : (
          entry.stale && <span className="stale">Out of date</span>
        )}
      </header>
      <p className="hero">
        {formatPct(entry.pct)} <span className="hero-label">full</span>
      </p>
      <p className="normal">{normalLine(entry)}</p>
      <p className="meta">
        As of {formatDate(entry.asOf)} · {entry.nReporting} of {entry.nTotal} reservoirs
      </p>
      {status?.note && <p className="status-note">{status.note}</p>}
      <p className="meta">
        Source:{' '}
        <a href={source.url} target="_blank" rel="noreferrer">
          {source.name}
        </a>
      </p>
    </article>
  )
}
