import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { css } from '../../styled-system/css'
import { formatOffset, MISCUE_LIMIT, spinZone, type SpinZone } from '../data/hitPoint'
import type { HitPoint } from '../data/types'
import { Ball } from './Ball'

function clamp(p: HitPoint): HitPoint {
  const d = Math.hypot(p.x, p.y)
  return d <= MISCUE_LIMIT ? p : { x: (p.x / d) * MISCUE_LIMIT, y: (p.y / d) * MISCUE_LIMIT }
}

const panelClass = css({
  bg: 'sunken',
  border: '2px solid',
  borderColor: 'line',
  borderRadius: '22px',
  overflow: 'hidden',
  flexShrink: 0,
})

// ---------------------------------------------------------------------------
// Front view: where the cue tip hits the cue ball. Click / drag / arrow keys.
// ---------------------------------------------------------------------------

const F = { w: 376, h: 332, cx: 188, cy: 166, r: 147.5 }

export function HitPointFront({ value, onChange }: { value: HitPoint; onChange: (p: HitPoint) => void }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const dragging = useRef(false)

  const update = (e: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const sx = ((e.clientX - rect.left) / rect.width) * F.w
    const sy = ((e.clientY - rect.top) / rect.height) * F.h
    onChange(clamp({ x: (sx - F.cx) / F.r, y: (F.cy - sy) / F.r }))
  }

  const onKeyDown = (e: KeyboardEvent<SVGSVGElement>) => {
    const step = e.shiftKey ? 0.25 : 0.05
    const delta: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    }
    if (e.key === 'Home') onChange({ x: 0, y: 0 })
    const d = delta[e.key]
    if (!d && e.key !== 'Home') return
    e.preventDefault()
    if (d) onChange(clamp({ x: value.x + d[0], y: value.y + d[1] }))
  }

  const mx = F.cx + value.x * F.r
  const my = F.cy - value.y * F.r

  return (
    <section className={panelClass} aria-label="Punkt uderzenia – czoło bili">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${F.w} ${F.h}`}
        className={css({
          display: 'block',
          w: 'full',
          h: 'auto',
          cursor: 'crosshair',
          touchAction: 'none',
          outline: 'none',
          '&:focus-visible circle[data-marker]': { stroke: 'text' },
        })}
        tabIndex={0}
        role="application"
        aria-roledescription="wybór punktu uderzenia"
        aria-label={`Punkt uderzenia: ${formatOffset(value.y)} w pionie, ${formatOffset(value.x)} w poziomie. Strzałki przesuwają punkt.`}
        onKeyDown={onKeyDown}
        onPointerDown={(e) => {
          dragging.current = true
          e.currentTarget.setPointerCapture(e.pointerId)
          update(e)
        }}
        onPointerMove={(e) => dragging.current && update(e)}
        onPointerUp={() => (dragging.current = false)}
        onPointerCancel={() => (dragging.current = false)}
      >
        <Ball ball={{ kind: 'cue' }} cx={F.cx} cy={F.cy} r={F.r} plain />
        <g fill="none" stroke="#8e9cab" strokeWidth="2.24" pointerEvents="none">
          <line x1={F.cx - 165.4} y1={F.cy} x2={F.cx + 165.4} y2={F.cy} strokeDasharray="8.94 11.18" opacity="0.45" />
          <line x1={F.cx} y1={F.cy - 165.4} x2={F.cx} y2={F.cy + 165.4} strokeDasharray="8.94 11.18" opacity="0.45" />
          <circle cx={F.cx} cy={F.cy} r={F.r * MISCUE_LIMIT} strokeDasharray="6.7 13.4" opacity="0.3" />
        </g>
        <circle data-marker cx={mx} cy={my} r="18.66" fill="#b8ff3c" stroke="#5a646f" strokeWidth="2.68" pointerEvents="none" />
      </svg>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Side view: vertical component of the hit point → naciąg / stop / śruba.
// ---------------------------------------------------------------------------

const S = { w: 379, h: 237, cx: 167, cy: 134, r: 63 }
// Hit point the Figma cue artwork was drawn against.
const CUE_ANCHOR = { x: 221.5, y: 102.1 }
const ZONES: { id: SpinZone; label: string; v: number }[] = [
  { id: 'naciag', label: 'Naciąg', v: 0.5 },
  { id: 'stop', label: 'Stop', v: 0 },
  { id: 'sruba', label: 'Śruba', v: -0.5 },
]

const mono = "'JetBrains Mono', ui-monospace, monospace"
const sans = "'Inter', ui-sans-serif, sans-serif"

export function HitPointSide({ value }: { value: HitPoint }) {
  const v = value.y
  const zone = spinZone(v)
  const hy = S.cy - v * S.r
  const hx = S.cx + Math.sqrt(Math.max(0, S.r ** 2 - (v * S.r) ** 2))
  const dx = hx - CUE_ANCHOR.x
  const dy = hy - CUE_ANCHOR.y
  const mirror = zone === 'sruba'

  return (
    <section className={panelClass} style={{ borderWidth: 1, borderRadius: 12 }} aria-label="Punkt uderzenia – widok z boku">
      <svg viewBox={`0 0 ${S.w} ${S.h}`} className={css({ display: 'block', w: 'full', h: 'auto' })} role="img"
        aria-label={`Widok z boku: ${ZONES.find((z) => z.id === zone)!.label}, przesunięcie ${formatOffset(v)}`}>
        {/* cloth */}
        <rect x="0" y={S.cy + S.r - 1} width={S.w} height="41" fill="#0f5c46" />
        <rect x="0" y={S.cy + S.r - 1} width={S.w} height="2" fill="#1d7a5e" />
        <rect x="0" y={S.h - 7} width={S.w} height="7" fill="#2a1b12" />

        <Ball ball={{ kind: 'cue' }} cx={S.cx} cy={S.cy} r={S.r} plain />

        {/* reference lines */}
        <g fill="none">
          {ZONES.map((z) => (
            <line key={z.id} x1="84" x2="335" y1={S.cy - z.v * S.r} y2={S.cy - z.v * S.r}
              stroke="#8e9cab" strokeWidth="1.12" strokeDasharray="5.6 5.6" opacity="0.35" />
          ))}
          <line x1={S.cx} x2={S.cx} y1="57" y2="194" stroke="#8e9cab" strokeWidth="1.12" strokeDasharray="4.48 5.6" opacity="0.3" />
          <line x1="84" x2="335" y1={hy} y2={hy} stroke="#b8ff3c" strokeWidth="1.68" strokeDasharray="5.6 5.6" opacity="0.95" />
          {Math.abs(hy - S.cy) > 2 && (
            <g stroke="#b8ff3c">
              <line x1="86.4" x2="86.4" y1={hy} y2={S.cy} strokeWidth="1.12" opacity="0.7" />
              <path d={`M80.8 ${hy}H92 M80.8 ${S.cy}H92`} strokeWidth="1.68" opacity="0.9" />
            </g>
          )}
        </g>

        {/* spin direction */}
        {zone !== 'stop' && (
          <g transform={mirror ? `translate(${S.cx * 2} 0) scale(-1 1)` : undefined} fill="#4dd8ff">
            <path d={`M239 91.7 A83.5 83.5 0 0 0 102.4 81.1`} fill="none" stroke="#4dd8ff" strokeWidth="2.24" opacity="0.9" />
            <path d="M95.3 91.1L95.6 77L107.4 83.8Z" />
          </g>
        )}

        {/* cue stick, anchored at the hit point */}
        <g transform={`translate(${dx} ${dy})`}>
          <path d="M232.6 105.35L379.96 73.3L375.48 54.7L229.8 94.03Z" fill="#9c6b33" />
          <path d="M260.7 92.53L406.6 56.9" stroke="#fff" strokeWidth="1.68" opacity="0.18" />
          <path d="M232.58 105.12L255.55 99.97L252.75 88.2L230 94.25Z" fill="#efe4ce" />
          <path d="M224.75 106.53L232.49 105.07L229.91 94.2L222.4 96.55Z" fill="#2f6fa3" />
        </g>
        <circle cx={hx} cy={hy} r="14.57" fill="none" stroke="#b8ff3c" strokeWidth="1.68" strokeDasharray="3.36 3.36" />
        <circle cx={hx} cy={hy} r="6.16" fill="#b8ff3c" />

        {/* travel direction */}
        <path d="M46.1 214.8H149.2" stroke="#b8ff3c" strokeWidth="2.8" strokeLinecap="round" />
        <path d="M34.9 214.8L48.35 207.4V222.2Z" fill="#b8ff3c" />

        {/* labels */}
        <text x="15" y="27" fontFamily={sans} fontWeight="600" fontSize="12.33" letterSpacing="0.9" fill="#65727f">
          WIDOK Z BOKU
        </text>
        <text x={S.w - 14} y="29" textAnchor="end" fontFamily={mono} fontWeight="500" fontSize="14.57" fill="#b8ff3c">
          {formatOffset(v)}
        </text>
        {ZONES.map((z, i) => (
          <text key={z.id} x="15" y={105 + i * 31.5} fontFamily={sans} fontWeight="600" fontSize="12.33" letterSpacing="0.9"
            fill={z.id === zone ? '#b8ff3c' : '#65727f'}>
            {z.label.toUpperCase()}
          </text>
        ))}
      </svg>
    </section>
  )
}
