// Sequential single-hue (blue) ramp for % full: more water reads darker.
export const PCT_BINS = [
  { min: 0, max: 20, color: '#cde2fb' },
  { min: 20, max: 40, color: '#86b6ef' },
  { min: 40, max: 60, color: '#3987e5' },
  { min: 60, max: 80, color: '#1c5cab' },
  { min: 80, max: 100, color: '#0d366b' },
] as const

export const NOT_COVERED = '#e1e0d9'

export function pctColor(pct: number): string {
  const bin = PCT_BINS.find((b) => pct < b.max) ?? PCT_BINS[PCT_BINS.length - 1]
  return bin.color
}
