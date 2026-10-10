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
