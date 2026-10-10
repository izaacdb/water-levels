import { useEffect, useState } from 'react'
import type { Areas, Current, Manifest, Series } from '../contract'

const base = import.meta.env.BASE_URL

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base}${path}`)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export interface AppData {
  manifest: Manifest
  areas: Areas
  current: Current
}

export function loadAppData(): Promise<AppData> {
  return Promise.all([
    getJson<Manifest>('data/manifest.json'),
    getJson<Areas>('data/areas.json'),
    getJson<Current>('data/current.json'),
  ]).then(([manifest, areas, current]) => ({ manifest, areas, current }))
}

export type Loadable<T> = { status: 'loading' } | { status: 'error'; error: string } | { status: 'ready'; data: T }

export function useAppData(): Loadable<AppData> {
  const [state, setState] = useState<Loadable<AppData>>({ status: 'loading' })
  useEffect(() => {
    loadAppData().then(
      (data) => setState({ status: 'ready', data }),
      (err: unknown) => setState({ status: 'error', error: String(err) }),
    )
  }, [])
  return state
}

export const geoUrl = (name: string) => `${base}geo/${name}`

const seriesCache = new Map<string, Promise<Series>>()

export function loadSeries(areaId: string): Promise<Series> {
  let pending = seriesCache.get(areaId)
  if (!pending) {
    pending = getJson<Series>(`data/series/${encodeURIComponent(areaId)}.json`)
    pending.catch(() => seriesCache.delete(areaId))
    seriesCache.set(areaId, pending)
  }
  return pending
}

export function useSeries(areaId: string): Loadable<Series> {
  const [state, setState] = useState<{ id: string; value: Loadable<Series> }>({ id: areaId, value: { status: 'loading' } })
  useEffect(() => {
    let live = true
    loadSeries(areaId).then(
      (data) => live && setState({ id: areaId, value: { status: 'ready', data } }),
      (err: unknown) => live && setState({ id: areaId, value: { status: 'error', error: String(err) } }),
    )
    return () => {
      live = false
    }
  }, [areaId])
  return state.id === areaId ? state.value : { status: 'loading' }
}
