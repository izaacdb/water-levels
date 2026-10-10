import { Suspense, useEffect, useMemo, useState } from 'react'
import type { Area, Current, Series } from '../contract'
import { COMPARE_COLORS, type CompareItem, assignSlots } from '../lib/compare'
import { loadSeries } from '../lib/data'
import { countryName } from '../lib/format'
import type { Mode } from '../lib/scale'
import { MAX_COMPARE } from '../lib/urlState'
import { CompareChart } from './LazyCharts'
import { ModeToggle } from './ModeToggle'

const hm3 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })
const LEVEL = { country: 'Country', region: 'River basin', reservoir: 'Reservoir' } as const

interface Props {
  areas: Area[]
  current: Current
  ids: string[]
  mode: Mode
  onModeChange: (mode: Mode) => void
  onChange: (ids: string[]) => void
  onSelect: (id: string) => void
}

function useSeriesMany(ids: string[]): Map<string, Series> {
  const [loaded, setLoaded] = useState(() => new Map<string, Series>())
  useEffect(() => {
    let live = true
    Promise.all(ids.map((id) => loadSeries(id).then((s) => [id, s] as const))).then(
      (pairs) => live && setLoaded(new Map(pairs)),
      () => {},
    )
    return () => {
      live = false
    }
  }, [ids])
  return loaded
}

export function ComparePanel({ areas, current, ids, mode, onModeChange, onChange, onSelect }: Props) {
  const [query, setQuery] = useState('')
  // Colour slots follow each area across additions and removals.
  const [slots, setSlots] = useState(() => assignSlots(ids, new Map()))
  const [slotIds, setSlotIds] = useState(ids)
  if (slotIds !== ids) {
    setSlotIds(ids)
    setSlots(assignSlots(ids, slots))
  }
  const byId = useMemo(() => new Map(areas.map((a) => [a.id, a])), [areas])
  const chosen = ids.map((id) => byId.get(id)).filter((a): a is Area => !!a)
  const series = useSeriesMany(ids)
  const full = ids.length >= MAX_COMPARE

  const matches = useMemo(() => {
    const q = query.trim().toLocaleLowerCase()
    if (q.length < 2) return []
    return areas
      .filter((a) => current[a.id] && !ids.includes(a.id) && a.name.toLocaleLowerCase().includes(q))
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, 8)
  }, [query, areas, current, ids])

  const items: CompareItem[] = chosen
    .filter((a) => series.has(a.id))
    .map((area) => ({ area, series: series.get(area.id)!, slot: slots.get(area.id) ?? 0 }))

  return (
    <section className="compare" aria-label="Compare areas">
      <ol className="compare-list" aria-label="Areas being compared">
        {chosen.map((area) => (
          <li key={area.id} aria-label={area.name}>
            <span className="swatch" style={{ background: COMPARE_COLORS[slots.get(area.id) ?? 0] }} aria-hidden />
            <button type="button" className="compare-name link-button" onClick={() => onSelect(area.id)}>
              {area.name}
            </button>
            <span className="compare-sub">
              {area.level === 'country' ? 'Country' : `${LEVEL[area.level]} · ${countryName(area.country)}`} ·{' '}
              {hm3.format(area.capacityHm3)} hm³
            </span>
            <button
              type="button"
              className="remove"
              aria-label={`Remove ${area.name}`}
              onClick={() => onChange(ids.filter((id) => id !== area.id))}
            >
              ×
            </button>
          </li>
        ))}
      </ol>

      <label className="compare-search">
        Add an area
        <input
          type="search"
          value={query}
          placeholder={full ? 'Comparison is full' : 'Country, river basin or reservoir…'}
          disabled={full}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      {full && <p className="note">You can compare up to {MAX_COMPARE} areas. Remove one to add another.</p>}
      {matches.length > 0 && (
        <ul className="compare-results" aria-label="Matching areas">
          {matches.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => {
                  onChange([...ids, a.id])
                  setQuery('')
                }}
              >
                <span>{a.name}</span>
                <span className="compare-sub">
                  {a.level === 'country' ? 'Country' : `${LEVEL[a.level]} · ${countryName(a.country)}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {ids.length < 2 ? (
        <p className="note">
          {ids.length === 0
            ? 'Pick 2 to 5 areas — countries, river basins or reservoirs, from any country — to compare them on one chart.'
            : 'Add at least one more area to compare.'}
        </p>
      ) : (
        <>
          <ModeToggle mode={mode} onChange={onModeChange} />
          {items.length === chosen.length ? (
            <Suspense fallback={<div className="chart chart-loading">Loading chart…</div>}>
              <CompareChart items={items} mode={mode} />
            </Suspense>
          ) : (
            <div className="chart chart-loading">Loading history…</div>
          )}
          <p className="chart-note">
            Weekly, last 10 years. Percentages compare fairly across sizes: a small reservoir and a whole country
            are both shown as a share of their own capacity.
          </p>
        </>
      )}
    </section>
  )
}
