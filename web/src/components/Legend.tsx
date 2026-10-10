import { ANOM_BINS, INSUFFICIENT, NOT_COVERED, PCT_BINS, type Mode } from '../lib/scale'

export function Legend({ mode }: { mode: Mode }) {
  const bins = mode === 'pct' ? PCT_BINS : ANOM_BINS
  const caption = mode === 'pct' ? 'Reservoir storage, % full' : 'vs normal for this week (percentage points)'
  return (
    <figure className="legend" aria-label={`Map legend: ${caption}`}>
      <figcaption>{caption}</figcaption>
      <ol>
        {bins.map((b) => (
          <li key={b.label}>
            <span className="swatch" style={{ background: b.color }} aria-hidden />
            {b.label}
          </li>
        ))}
        {mode === 'anom' && (
          <li>
            <span className="swatch" style={{ background: INSUFFICIENT }} aria-hidden />
            Insufficient history (under 5 years)
          </li>
        )}
        <li>
          <span className="swatch" style={{ background: NOT_COVERED }} aria-hidden />
          Not covered
        </li>
      </ol>
    </figure>
  )
}
