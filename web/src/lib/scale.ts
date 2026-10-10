import type { CurrentEntry } from '../contract'

export type Mode = 'pct' | 'anom'

// % full: sequential single hue (blue), more water reads darker.
export const PCT_BINS = [
  { min: 0, max: 20, color: '#cde2fb', label: '0–20%' },
  { min: 20, max: 40, color: '#86b6ef', label: '20–40%' },
  { min: 40, max: 60, color: '#3987e5', label: '40–60%' },
  { min: 60, max: 80, color: '#1c5cab', label: '60–80%' },
  { min: 80, max: Infinity, color: '#0d366b', label: '80–100%' },
] as const

// vs normal: diverging red (drier than normal) ↔ grey ↔ blue (wetter), equal arms.
export const ANOM_BINS = [
  { min: -Infinity, max: -20, color: '#a32727', label: '20+ pts below' },
  { min: -20, max: -10, color: '#e34948', label: '10–20 below' },
  { min: -10, max: -3, color: '#f4aca9', label: '3–10 below' },
  { min: -3, max: 3, color: '#f0efec', label: 'Near normal' },
  { min: 3, max: 10, color: '#9ec5f4', label: '3–10 above' },
  { min: 10, max: 20, color: '#3987e5', label: '10–20 above' },
  { min: 20, max: Infinity, color: '#184f95', label: '20+ pts above' },
] as const

export const NOT_COVERED = '#e1e0d9'
export const INSUFFICIENT = '#b5b3ab'

function binColor(bins: readonly { max: number; color: string }[], value: number): string {
  return (bins.find((b) => value < b.max) ?? bins[bins.length - 1]).color
}

export const pctColor = (pct: number) => binColor(PCT_BINS, pct)
export const anomalyColor = (pts: number) => binColor(ANOM_BINS, pts)

export function colorFor(entry: CurrentEntry | undefined, mode: Mode): string {
  if (!entry) return NOT_COVERED
  if (mode === 'pct') return pctColor(entry.pct)
  return entry.anomalyPts == null ? INSUFFICIENT : anomalyColor(entry.anomalyPts)
}
