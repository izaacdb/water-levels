import type { Area, Current } from '../contract'
import { countryName, formatAnomaly, formatDate, formatPct } from '../lib/format'
import { type RankOptions, type Ranked, rankAreas } from '../lib/rankings'
import { colorFor } from '../lib/scale'

interface Props {
  areas: Area[]
  current: Current
  opts: RankOptions
  onChange: (opts: RankOptions) => void
  onSelect: (id: string) => void
}

function Row({ row, index, sort, onSelect }: { row: Ranked; index?: number; sort: RankOptions['sort']; onSelect: (id: string) => void }) {
  const value =
    sort === 'pct' ? formatPct(row.entry.pct) : row.entry.anomalyPts == null ? '—' : formatAnomaly(row.entry.anomalyPts)
  return (
    <li>
      <button type="button" className="rank-row" onClick={() => onSelect(row.area.id)}>
        {index != null && <span className="rank-index">{index + 1}</span>}
        <span className="swatch" style={{ background: colorFor(row.entry, sort) }} aria-hidden />
        <span className="rank-text">
          <span className="rank-name">{row.area.name}</span>
          <span className="rank-sub">
            {row.area.level === 'country' ? 'Country' : countryName(row.area.country)}
            {row.entry.stale && ` · last ${formatDate(row.entry.asOf)}`}
          </span>
        </span>
        <span className="rank-value">{value}</span>
      </button>
    </li>
  )
}

export function Rankings({ areas, current, opts, onChange: setOpts, onSelect }: Props) {
  const { ranked, awaiting, unranked } = rankAreas(areas, current, opts)
  return (
    <section className="rankings" aria-label="Rankings">
      <div className="rank-controls">
        <label>
          Level
          <select value={opts.level} onChange={(e) => setOpts({ ...opts, level: e.target.value as RankOptions['level'] })}>
            <option value="country">Countries</option>
            <option value="region">River basins</option>
            <option value="reservoir">Reservoirs</option>
          </select>
        </label>
        <label>
          Sort by
          <select value={opts.sort} onChange={(e) => setOpts({ ...opts, sort: e.target.value as RankOptions['sort'] })}>
            <option value="pct">% full</option>
            <option value="anom">vs normal</option>
          </select>
        </label>
        <button
          type="button"
          className="dir-button"
          onClick={() => setOpts({ ...opts, dir: opts.dir === 'desc' ? 'asc' : 'desc' })}
        >
          {opts.dir === 'desc' ? 'Highest first ↓' : 'Lowest first ↑'}
        </button>
      </div>
      <ol className="rank-list" aria-label="Ranked areas">
        {ranked.map((row, i) => (
          <Row key={row.area.id} row={row} index={i} sort={opts.sort} onSelect={onSelect} />
        ))}
      </ol>
      {unranked.length > 0 && (
        <>
          <h3>Insufficient history to compare with normal</h3>
          <ul className="rank-list" aria-label="Insufficient history">
            {unranked.map((row) => (
              <Row key={row.area.id} row={row} sort={opts.sort} onSelect={onSelect} />
            ))}
          </ul>
        </>
      )}
      {awaiting.length > 0 && (
        <>
          <h3>Awaiting update</h3>
          <ul className="rank-list" aria-label="Awaiting update">
            {awaiting.map((row) => (
              <Row key={row.area.id} row={row} sort={opts.sort} onSelect={onSelect} />
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
