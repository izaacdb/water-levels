import type { CountryStatus, CurrentEntry, SourceInfo } from '../contract'
import { formatDate, formatPct, sourceLabel } from '../lib/format'
import { pctColor } from '../lib/scale'
import { normalLine } from '../lib/tooltip'
import { SourceLinks } from './SourceLinks'

interface Props {
  name: string
  entry: CurrentEntry
  sources: SourceInfo[]
  status?: CountryStatus
  /** Opens the country's detail; the title becomes the button (no nested controls). */
  onOpen?: () => void
}

export function CountryCard({ name, entry, sources, status, onOpen }: Props) {
  const withdrawn = status?.status === 'withdrawn'
  return (
    <article className="card">
      <header className="card-head">
        <span className="swatch" style={{ background: pctColor(entry.pct) }} aria-hidden />
        <h2>
          {onOpen ? (
            <button type="button" className="card-title" onClick={onOpen}>
              {name}
            </button>
          ) : (
            name
          )}
        </h2>
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
        {sourceLabel(sources)}: <SourceLinks sources={sources} />
      </p>
    </article>
  )
}
