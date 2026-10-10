import { NOT_COVERED, PCT_BINS } from '../lib/scale'

export function Legend() {
  return (
    <figure className="legend" aria-label="Map legend: reservoir storage, % of capacity">
      <figcaption>Reservoir storage, % full</figcaption>
      <ol>
        {PCT_BINS.map((b) => (
          <li key={b.min}>
            <span className="swatch" style={{ background: b.color }} aria-hidden />
            {b.min}–{b.max}%
          </li>
        ))}
        <li>
          <span className="swatch" style={{ background: NOT_COVERED }} aria-hidden />
          Not covered
        </li>
      </ol>
    </figure>
  )
}
