import { useCallback, useEffect, useMemo, useState } from 'react'
import { AreaDetail } from './components/AreaDetail'
import { ComparePanel } from './components/ComparePanel'
import { CountryCard } from './components/CountryCard'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { ModeToggle } from './components/ModeToggle'
import { Rankings } from './components/Rankings'
import type { AppData } from './lib/data'
import { useAppData } from './lib/data'
import { formatWeek } from './lib/format'
import { MAX_COMPARE, type MapPosition, type ViewState, validateState } from './lib/urlState'
import { useUrlState } from './lib/useUrlState'

interface PanelProps {
  data: AppData
  state: ViewState
  update: (patch: Partial<ViewState>) => void
}

function Panel({ data, state, update }: PanelProps) {
  const sourceFor = (sourceId: string) => data.manifest.sources.find((s) => s.id === sourceId)
  const select = (id: string) => update({ area: id })
  const addToCompare = (id: string) =>
    update({ cmp: state.cmp.includes(id) ? state.cmp : [...state.cmp, id].slice(0, MAX_COMPARE), view: 'compare', area: null })

  const area = state.area ? data.areas.find((a) => a.id === state.area) : undefined
  const entry = area ? data.current[area.id] : undefined
  if (area && entry) {
    return (
      <AreaDetail
        key={area.id}
        area={area}
        entry={entry}
        source={sourceFor(area.sourceId)}
        parent={data.areas.find((a) => a.id === area.parentId)}
        onBack={() => update({ area: null })}
        onSelect={select}
        countryNote={data.manifest.countries.find((c) => c.code === area.country)?.note ?? undefined}
        onCompare={state.cmp.includes(area.id) || state.cmp.length >= MAX_COMPARE ? undefined : () => addToCompare(area.id)}
      />
    )
  }

  const tabs = [
    ['overview', 'Overview'],
    ['rankings', 'Rankings'],
    ['compare', state.cmp.length ? `Compare (${state.cmp.length})` : 'Compare'],
  ] as const

  return (
    <>
      <nav className="tabs" aria-label="Panel">
        {tabs.map(([view, label]) => (
          <button key={view} type="button" aria-pressed={state.view === view} onClick={() => update({ view })}>
            {label}
          </button>
        ))}
      </nav>
      {state.view === 'rankings' && (
        <Rankings
          areas={data.areas}
          current={data.current}
          opts={{ level: state.level, sort: state.sort, dir: state.dir }}
          onChange={(opts) => update(opts)}
          onSelect={select}
        />
      )}
      {state.view === 'compare' && (
        <ComparePanel
          areas={data.areas}
          current={data.current}
          ids={state.cmp}
          mode={state.mode}
          onModeChange={(mode) => update({ mode })}
          onChange={(cmp) => update({ cmp })}
          onSelect={select}
        />
      )}
      {state.view === 'overview' && (
        <>
          <ModeToggle mode={state.mode} onChange={(mode) => update({ mode })} />
          {data.areas
            .filter((a) => a.level === 'country')
            .map((country) => {
              const countryEntry = data.current[country.id]
              const source = sourceFor(country.sourceId)
              return countryEntry && source ? (
                <button type="button" key={country.id} className="card-button" onClick={() => select(country.id)}>
                  <CountryCard
                    name={country.name}
                    entry={countryEntry}
                    source={source}
                    status={data.manifest.countries.find((c) => c.code === country.id)}
                  />
                </button>
              ) : null
            })}
          <Legend mode={state.mode} />
          <p className="note">Zoom in to see river basins, then individual reservoirs. Click any area for its history.</p>
          <p className="note">
            Grey countries are not covered: they don't publish official per-reservoir data at least weekly.
          </p>
        </>
      )}
    </>
  )
}

function Explorer({ data }: { data: AppData }) {
  const [raw, update] = useUrlState()
  const known = useMemo(() => new Set(data.areas.map((a) => a.id)), [data.areas])
  // E7: a shared link may name areas that have since been renamed or removed.
  const [arrival] = useState(() => validateState(raw, known))
  const missing = arrival.missing
  const [noticeOpen, setNoticeOpen] = useState(missing.length > 0)
  const state = validateState(raw, known).state
  useEffect(() => {
    // Clean the URL once, on arrival, so a re-shared link is tidy.
    if (arrival.missing.length) update({ area: arrival.state.area, cmp: arrival.state.cmp })
  }, [arrival, update])
  const onMove = useCallback((at: MapPosition) => update({ at }), [update])
  const onSelect = useCallback((id: string) => update({ area: id }), [update])
  const names = (ids: string[]) => ids.join(', ')

  return (
    <main className="layout">
      <MapView
        areas={data.areas}
        current={data.current}
        mode={state.mode}
        onSelect={onSelect}
        initialAt={state.at}
        onMove={onMove}
      />
      <aside className="panel">
        {noticeOpen && (
          <div className="notice" role="status">
            <span>
              Some areas in this link no longer exist and were left out: <strong>{names(missing)}</strong>
            </span>
            <button type="button" className="link-button" onClick={() => setNoticeOpen(false)}>
              Dismiss
            </button>
          </div>
        )}
        <Panel data={data} state={state} update={update} />
      </aside>
    </main>
  )
}

export default function App() {
  const state = useAppData()
  return (
    <div className="app">
      <header className="topbar">
        <h1>Europe's reservoirs</h1>
        {state.status === 'ready' && (
          <span className="badge" title="All figures are placed on a common weekly snapshot">
            {formatWeek(state.data.manifest.snapshotWeek)}
          </span>
        )}
      </header>
      {state.status === 'loading' && <p className="status">Loading the latest official data…</p>}
      {state.status === 'error' && <p className="status error">Couldn't load data: {state.error}</p>}
      {state.status === 'ready' && <Explorer data={state.data} />}
    </div>
  )
}
