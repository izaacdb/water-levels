const dateFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

export function formatDate(iso: string): string {
  return dateFmt.format(new Date(`${iso}T00:00:00Z`))
}

export function formatPct(pct: number): string {
  return `${pct.toFixed(1)}%`
}

/** "2026-W41" → "Week 41, 2026" */
export function formatWeek(isoWeek: string): string {
  const [year, week] = isoWeek.split('-W')
  return `Week ${Number(week)}, ${year}`
}

/** +12.3 pts / −4.0 pts (true minus sign). */
export function formatAnomaly(pts: number): string {
  // Round the magnitude so −4.25 and +4.25 round the same way.
  const magnitude = Math.round(Math.abs(pts) * 10) / 10
  const sign = magnitude === 0 ? '±' : pts > 0 ? '+' : '−'
  return `${sign}${magnitude.toFixed(1)} pts`
}

const COUNTRY_NAMES: Record<string, string> = {
  ES: 'Spain',
  PT: 'Portugal',
  BG: 'Bulgaria',
  CY: 'Cyprus',
  CZ: 'Czechia',
  UK: 'United Kingdom',
  EL: 'Greece',
  DE: 'Germany',
}

export const countryName = (code: string) => COUNTRY_NAMES[code] ?? code

/** "Source"/"Sources" label for one or several official sources (B2′). */
export const sourceLabel = (sources: unknown[]) => (sources.length > 1 ? 'Sources' : 'Source')

/** B25: what a published-total area is, wherever its figure appears. */
export const TOTAL_ONLY_NOTE =
  'Published as one total for all the operator’s reservoirs: there are no per-reservoir figures or capacity, and it isn’t added into the country total.'
