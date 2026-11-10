import { css } from '../../styled-system/css'
import type { Point, ShotSuggestion, TableBall } from '../data/types'
import { Ball } from './Ball'

// Geometry of the Figma "Pool Table" component (896×476, felt 840×420 inset by 28).
const W = 896
const H = 476
const INSET = 28
const FELT_W = 840
const FELT_H = 420

const fx = (x: number) => INSET + x * FELT_W
const fy = (y: number) => INSET + y * FELT_H
const toPx = ([x, y]: Point): Point => [fx(x), fy(y)]

const DIAMOND_X = [133, 238, 343, 553, 658, 763]
const DIAMOND_Y = [133, 238, 343]
const POCKETS: Point[] = [
  [0, 0],
  [0.5, 0],
  [1, 0],
  [0, 1],
  [0.5, 1],
  [1, 1],
]
const GHOSTS = [
  { at: 0.3, opacity: 0.1 },
  { at: 0.55, opacity: 0.2 },
  { at: 0.8, opacity: 0.3 },
]

const tableClass = css({
  display: 'block',
  width: '100%',
  height: 'auto',
  maxWidth: `${W}px`,
  overflow: 'visible',
  filter: 'drop-shadow(0 18px 24px rgba(0, 0, 0, 0.6))',
})

interface PoolTableProps {
  balls: TableBall[]
  shot?: ShotSuggestion | null
  label?: string
}

export function PoolTable({ balls, shot, label = 'Aktualne ustawienie bil na stole' }: PoolTableProps) {
  return (
    <svg className={tableClass} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {/* rail */}
      <rect x="1" y="1" width={W - 2} height={H - 2} rx="21" fill="#2a1b12" stroke="#432d1d" strokeWidth="2" />
      {/* felt + cushion */}
      <rect x={INSET} y={INSET} width={FELT_W} height={FELT_H} rx="6" fill="#0f5c46" filter="url(#eb-felt-fx)" />
      <rect x={INSET - 2} y={INSET - 2} width={FELT_W + 4} height={FELT_H + 4} rx="6" fill="none" stroke="#0a4231" strokeWidth="4" />
      {/* head string and spots */}
      <rect x={fx(0.25) - 1} y={INSET} width="2" height={FELT_H} fill="#1d7a5e" opacity="0.5" />
      <circle cx={fx(0.25)} cy={fy(0.5)} r="4" fill="#1d7a5e" opacity="0.7" />
      <circle cx={fx(0.75)} cy={fy(0.5)} r="4" fill="#1d7a5e" opacity="0.7" />
      {/* diamonds */}
      <g fill="#e2d3ae" fillOpacity="0.42">
        {DIAMOND_X.map((x) => [14, H - 14].map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r="4" />))}
        {DIAMOND_Y.map((y) => [14, W - 14].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="4" />))}
      </g>
      {/* pockets */}
      {POCKETS.map((p) => {
        const [cx, cy] = toPx(p)
        return (
          <circle
            key={`${cx}-${cy}`}
            cx={cx}
            cy={cy}
            r="18.5"
            fill="#06090c"
            stroke="#432d1d"
            strokeWidth="3"
            filter="url(#eb-pocket-fx)"
          />
        )
      })}

      {shot && <ShotTrace shot={shot} balls={balls} />}

      {balls.map((b) => (
        <Ball key={b.id} ball={b} cx={fx(b.x)} cy={fy(b.y)} r={b.radius * FELT_H} />
      ))}
    </svg>
  )
}

function ShotTrace({ shot, balls }: { shot: ShotSuggestion; balls: TableBall[] }) {
  const cue = shot.cue_path.map(toPx)
  const target = shot.target_path.map(toPx)
  const targetBall = balls.find((b) => b.id === shot.target_ball_id)
  const cueBall = balls.find((b) => b.kind === 'cue')
  const r = (cueBall?.radius ?? 15 / FELT_H) * FELT_H
  const [start, end] = [cue[0], cue[cue.length - 1]]
  const line = (pts: Point[]) => pts.map((p) => p.join(',')).join(' ')

  return (
    <g pointerEvents="none">
      <polyline points={line(cue)} fill="none" stroke="#4dd8ff" strokeWidth="2.5" strokeDasharray="9 8" strokeLinecap="round" />
      <polyline points={line(target)} fill="none" stroke="#b8ff3c" strokeWidth="2.5" strokeDasharray="9 8" strokeLinecap="round" />
      {targetBall && (
        <circle
          cx={fx(targetBall.x)}
          cy={fy(targetBall.y)}
          r={r + 4}
          fill="none"
          stroke="#4dd8ff"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
      )}
      {GHOSTS.map(({ at, opacity }) => (
        <circle
          key={at}
          cx={start[0] + (end[0] - start[0]) * at}
          cy={start[1] + (end[1] - start[1]) * at}
          r={r}
          fill="#f7f4ec"
          fillOpacity={opacity}
        />
      ))}
    </g>
  )
}
