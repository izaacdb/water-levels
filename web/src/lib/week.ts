export function isoWeekParts(label: string): { year: number; week: number } {
  const [year, week] = label.split('-W')
  return { year: Number(year), week: Number(week) }
}

/** Monday (UTC) of an ISO week label such as "2026-W41". */
export function isoWeekStart(label: string): Date {
  const { year, week } = isoWeekParts(label)
  // ISO week 1 is the week containing 4 January.
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const mondayOfWeek1 = jan4.getTime() - ((jan4.getUTCDay() + 6) % 7) * 86_400_000
  return new Date(mondayOfWeek1 + (week - 1) * 7 * 86_400_000)
}
