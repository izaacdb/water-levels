import { useState } from 'react'
import { AreaDetail } from './components/AreaDetail'
import { CountryCard } from './components/CountryCard'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { ModeToggle } from './components/ModeToggle'
import { Rankings } from './components/Rankings'
import type { AppData } from './lib/data'
import { useAppData } from './lib/data'
import { formatWeek } from './lib/format'
import type { Mode } from './lib/scale'

type View = { kind: 'overview' } | { kind: 'rankings' } | { kind: 'area'; id: string; from: 'overview' | 'rankings' }

function Panel({ data, mode, setMode, view, setView }: {
  data: AppData
  mode: Mode
  setMode: (m: Mode) => void
  view: View
  setView: (v: View) => void
}) {
  const sourceFor = (sourceId: string) => data.manifest.sources.find((s) => s.id === sourceId)
  const tab = view.kind === 'area' ? view.from : view.kind
  const select = (id: string) => setView({ kind: 'area', id, from: tab })

  if (view.kind === 'area') {
    const area = data.areas.find((a) => a.id === view.id)
    const entry = data.current[view.id]
    if (area && entry) {
      return (
        <AreaDetail
          key={area.id}
          area={area}
          entry={entry}
          source={sourceFor(area.sourceId)}
          parent={data.areas.find((a) => a.id === area.parentId)}
          onBack={() => setView({ kind: view.from })}
          onSelect={select}
        />
      )
    }
  }

  return (
    <>
      <nav className="tabs" aria-label="Panel">
        <button type="button" aria-pressed={tab === 'overview'} onClick={() => setView({ kind: 'overview' })}>
          Overview
        </button>
        <button type="button" aria-pressed={tab === 'rankings'} onClick={() => setView({ kind: 'rankings' })}>
          Rankings
        </button>
      </nav>
      {tab === 'rankings' ? (
        <Rankings areas={data.areas} current={data.current} onSelect={select} />
      ) : (
        <>
          <ModeToggle mode={mode} onChange={setMode} />
          {data.areas
            .filter((a) => a.level === 'country')
            .map((area) => {
              const entry = data.current[area.id]
              const source = sourceFor(area.sourceId)
              return entry && source ? (
                <button type="button" key={area.id} className="card-button" onClick={() => select(area.id)}>
                  <CountryCard name={area.name} entry={entry} source={source} />
                </button>
              ) : null
            })}
          <Legend mode={mode} />
          <p className="note">Zoom in to see river basins, then individual reservoirs. Click any area for its history.</p>
          <p className="note">
            Grey countries are not covered: they don't publish official per-reservoir data at least weekly.
          </p>
        </>
      )}
    </>
  )
}

export default function App() {
  const state = useAppData()
  const [mode, setMode] = useState<Mode>('pct')
  const [view, setView] = useState<View>({ kind: 'overview' })

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

      {state.status === 'ready' && (
        <main className="layout">
          <MapView
            areas={state.data.areas}
            current={state.data.current}
            mode={mode}
            onSelect={(id) => setView({ kind: 'area', id, from: view.kind === 'rankings' ? 'rankings' : 'overview' })}
          />
          <aside className="panel">
            <Panel data={state.data} mode={mode} setMode={setMode} view={view} setView={setView} />
          </aside>
        </main>
      )}
    </div>
  )
}
