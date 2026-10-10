import { CountryCard } from './components/CountryCard'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { formatWeek } from './lib/format'
import { useAppData } from './lib/data'

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

      {state.status === 'ready' && (
        <main className="layout">
          <MapView current={state.data.current} />
          <aside className="panel">
            {state.data.areas
              .filter((a) => a.level === 'country')
              .map((area) => {
                const entry = state.data.current[area.id]
                const source = state.data.manifest.sources.find((s) => s.id === area.sourceId)
                return entry && source ? (
                  <CountryCard key={area.id} name={area.name} entry={entry} source={source} />
                ) : null
              })}
            <Legend />
            <p className="note">
              Grey countries are not covered: they don't publish official per-reservoir data at least
              weekly.
            </p>
          </aside>
        </main>
      )}
    </div>
  )
}
