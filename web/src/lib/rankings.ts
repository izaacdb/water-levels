import type { Area, Current, CurrentEntry } from '../contract'

export interface RankOptions {
  level: Area['level']
  sort: 'pct' | 'anom'
  dir: 'asc' | 'desc'
}

export interface Ranked {
  area: Area
  entry: CurrentEntry
}

export interface Rankings {
  ranked: Ranked[]
  /** B15: stale areas, listed apart as "awaiting update". */
  awaiting: Ranked[]
  /** E2: no normal yet, so they can't be ranked by vs normal. */
  unranked: Ranked[]
}

export function rankAreas(areas: Area[], current: Current, opts: RankOptions): Rankings {
  const rows = areas
    .filter((a) => a.level === opts.level && current[a.id])
    .map((area) => ({ area, entry: current[area.id] }))
  const fresh = rows.filter((r) => !r.entry.stale)
  const value = (r: Ranked) => (opts.sort === 'pct' ? r.entry.pct : r.entry.anomalyPts)
  const sign = opts.dir === 'asc' ? 1 : -1
  return {
    ranked: fresh
      .filter((r) => value(r) != null)
      .sort((a, b) => sign * ((value(a) as number) - (value(b) as number)) || a.area.name.localeCompare(b.area.name)),
    awaiting: rows.filter((r) => r.entry.stale).sort((a, b) => a.area.name.localeCompare(b.area.name)),
    unranked: fresh.filter((r) => value(r) == null).sort((a, b) => a.area.name.localeCompare(b.area.name)),
  }
}
