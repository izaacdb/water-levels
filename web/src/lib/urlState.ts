import type { Area } from '../contract'
import type { Mode } from './scale'

export const MAX_COMPARE = 5

export interface MapPosition {
  zoom: number
  lat: number
  lon: number
}

/** Everything that defines a view; serialised into the URL so links reproduce it (B22). */
export interface ViewState {
  mode: Mode
  view: 'overview' | 'rankings' | 'compare'
  area: string | null
  level: Area['level']
  sort: Mode
  dir: 'asc' | 'desc'
  cmp: string[]
  at: MapPosition | null
}

export const DEFAULT_STATE: ViewState = {
  mode: 'pct',
  view: 'overview',
  area: null,
  level: 'region',
  sort: 'pct',
  dir: 'desc',
  cmp: [],
  at: null,
}

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}

function parseAt(raw: string | null): MapPosition | null {
  if (!raw) return null
  const [zoom, lat, lon] = raw.split('/').map(Number)
  if (![zoom, lat, lon].every(Number.isFinite)) return null
  return { zoom, lat, lon }
}

export function parseState(search: string): ViewState {
  const q = new URLSearchParams(search)
  const cmp = [...new Set((q.get('cmp') ?? '').split(',').filter(Boolean))].slice(0, MAX_COMPARE)
  return {
    mode: oneOf(q.get('mode'), ['pct', 'anom'], DEFAULT_STATE.mode),
    view: oneOf(q.get('view'), ['overview', 'rankings', 'compare'], DEFAULT_STATE.view),
    area: q.get('area') || null,
    level: oneOf(q.get('level'), ['country', 'region', 'reservoir'], DEFAULT_STATE.level),
    sort: oneOf(q.get('sort'), ['pct', 'anom'], DEFAULT_STATE.sort),
    dir: oneOf(q.get('dir'), ['asc', 'desc'], DEFAULT_STATE.dir),
    cmp,
    at: parseAt(q.get('at')),
  }
}

export function serializeState(state: ViewState): string {
  const q = new URLSearchParams()
  const keys = ['mode', 'view', 'area', 'level', 'sort', 'dir'] as const
  for (const key of keys) {
    if (state[key] !== DEFAULT_STATE[key] && state[key] != null) q.set(key, String(state[key]))
  }
  if (state.cmp.length) q.set('cmp', state.cmp.join(','))
  if (state.at) {
    const { zoom, lat, lon } = state.at
    q.set('at', `${zoom.toFixed(2).replace(/\.?0+$/, '')}/${lat.toFixed(4).replace(/\.?0+$/, '')}/${lon.toFixed(4).replace(/\.?0+$/, '')}`)
  }
  const s = q.toString().replaceAll('%2C', ',').replaceAll('%2F', '/')
  return s ? `?${s}` : ''
}

/** E7: drop ids that no longer exist (renamed/removed areas) and report them. */
export function validateState(state: ViewState, known: Set<string>): { state: ViewState; missing: string[] } {
  const missing: string[] = []
  const area = state.area && !known.has(state.area) ? (missing.push(state.area), null) : state.area
  const cmp = state.cmp.filter((id) => known.has(id) || (missing.push(id), false))
  return { state: { ...state, area, cmp }, missing }
}
