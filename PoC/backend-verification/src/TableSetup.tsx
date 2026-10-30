import { useState } from 'react'
import type { Settings } from './types'

export default function TableSetup({ settings, onChange }: {
  settings: Settings; onChange: (settings: Settings) => void
}) {
  const [length, setLength] = useState('')
  const [width, setWidth] = useState('')
  const [diameter, setDiameter] = useState('')
  const [error, setError] = useState('')

  function apply() {
    const l = Number(length), w = Number(width), d = Number(diameter)
    const ratio = l / w, radius = d / (2 * w)
    if (![l, w, d].every(value => Number.isFinite(value) && value > 0)
      || ratio < 1 || ratio > 3 || radius < .012 || radius > .06) {
      setError('Enter positive measurements in the same unit: length / width must be 1–3 and ball diameter / width 2.4–12%.')
      return
    }
    setError('')
    onChange({ ...settings, table_ratio: ratio, ball_radius_ratio: radius })
  }

  return <section className="settings-section">
    <h3>Table setup</h3>
    <p>Measure the playing surface between the cushion noses and the ball diameter, using the same unit for all three. Corners map the long side from left to right. These measurements set the proportions and expected ball size for detection and shots.</p>
    <div className="table-measurements">
      <label>Cloth length<input type="number" min="0" step="any" value={length} onChange={e => setLength(e.target.value)} /></label>
      <label>Cloth width<input type="number" min="0" step="any" value={width} onChange={e => setWidth(e.target.value)} /></label>
      <label>Ball diameter<input type="number" min="0" step="any" value={diameter} onChange={e => setDiameter(e.target.value)} /></label>
    </div>
    <button className="secondary-button" onClick={apply}>Apply table dimensions</button>
    {error && <p role="alert">{error}</p>}
    <label className="checkbox-label"><input type="checkbox" checked={settings.cloth_hue === null}
      onChange={e => onChange({ ...settings, cloth_hue: e.target.checked ? null : 90 })} /> Detect cloth color automatically</label>
    {settings.cloth_hue !== null && <label className="range-label"><span>Cloth hue <strong>{settings.cloth_hue} / 179</strong></span>
      <input aria-label="Cloth hue" type="range" min="0" max="179" value={settings.cloth_hue}
        onChange={e => onChange({ ...settings, cloth_hue: Number(e.target.value) })} /></label>}
    <label className="range-label"><span>Minimum cloth saturation <strong>{settings.saturation_min} / 255</strong></span>
      <input aria-label="Minimum cloth saturation" type="range" min="15" max="180" value={settings.saturation_min}
        onChange={e => onChange({ ...settings, saturation_min: Number(e.target.value) })} /></label>
    <p>Automatic corners use the visible cloth boundary. Use manual corners if the boundary is ambiguous. For a photo, choose “Apply to image” after changing settings.</p>
  </section>
}
