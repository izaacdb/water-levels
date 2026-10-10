import type { Mode } from '../lib/scale'

const OPTIONS: { value: Mode; label: string }[] = [
  { value: 'pct', label: '% full' },
  { value: 'anom', label: 'vs normal' },
]

export function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  return (
    <fieldset className="toggle">
      <legend className="visually-hidden">Map shows</legend>
      {OPTIONS.map((o) => (
        <label key={o.value} className={mode === o.value ? 'active' : undefined}>
          <input
            type="radio"
            name="map-mode"
            value={o.value}
            checked={mode === o.value}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </fieldset>
  )
}
