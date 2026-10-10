import type { Area, CurrentEntry } from '../contract'
import { countryName, formatAnomaly, formatDate, formatPct } from './format'

const LEVEL_LABEL: Record<Area['level'], string> = {
  country: 'Country',
  region: 'River basin',
  reservoir: 'Reservoir',
}

export interface Tooltip {
  title: string
  subtitle: string
  lines: string[]
  stale: boolean
}

export function normalLine(entry: CurrentEntry): string {
  if (entry.anomalyPts == null) return 'vs normal: insufficient history'
  const years = entry.normalYears ?? 0
  const basis = years < 10 ? ` (based on ${years} years)` : ''
  return `${formatAnomaly(entry.anomalyPts)} vs normal${basis}`
}

const FLAG_NOTES: Record<string, string> = {
  over_capacity: 'Reported value exceeds capacity',
  negative: 'Reported value is negative',
}

/** E4: notes for readings shown as published but left out of totals. */
export function flagNotes(entry: CurrentEntry): string[] {
  return (entry.flags ?? []).map((f) => FLAG_NOTES[f] ?? f)
}

export function tooltipLines(area: Area, entry: CurrentEntry): Tooltip {
  const lines = [`${formatPct(entry.pct)} full`, normalLine(entry), `As of ${formatDate(entry.asOf)}`]
  if (area.level !== 'reservoir') lines.push(`${entry.nReporting} of ${entry.nTotal} reservoirs reporting`)
  lines.push(...flagNotes(entry))
  return {
    title: area.name,
    subtitle: area.level === 'country' ? LEVEL_LABEL.country : `${LEVEL_LABEL[area.level]} · ${countryName(area.country)}`,
    lines,
    stale: entry.stale,
  }
}
