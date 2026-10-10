import { useRef } from 'react'
import type { Ball, Frame, Point } from './types'

export default function SourceView({ frame, corners, editing, onCorners, balls, selected, onSelect, showLabels = false }: {
  frame: Frame; corners: Point[]; editing: boolean; onCorners: (corners: Point[]) => void;
  balls: Ball[]; selected: number | null; onSelect: (id: number) => void; showLabels?: boolean;
}) {
  const drag = useRef<number | null>(null)
  const point = (event: React.PointerEvent<SVGSVGElement>): Point => {
    const svg = event.currentTarget, cursor = svg.createSVGPoint()
    cursor.x = event.clientX; cursor.y = event.clientY
    const local = cursor.matrixTransform(svg.getScreenCTM()!.inverse())
    return { x: Math.max(0, Math.min(1, local.x / frame.width)), y: Math.max(0, Math.min(1, local.y / frame.height)) }
  }
  return <div className={`source-image ${editing ? 'editing' : ''}`} style={{ aspectRatio: `${frame.width}/${frame.height}` }}>
    <img src={frame.image} alt={frame.synthetic ? 'Synthetic angled pool table used to exercise the vision pipeline' : 'Uploaded pool table frame'} draggable={false} />
    <svg viewBox={`0 0 ${frame.width} ${frame.height}`} aria-label="Table calibration. Click four corners clockwise, with the first edge along the long side; drag markers to adjust." onPointerDown={event => {
      if (!editing) return
      const next = point(event)
      const near = corners.findIndex(p => Math.hypot((p.x - next.x) * event.currentTarget.clientWidth, (p.y - next.y) * event.currentTarget.clientHeight) < 22)
      if (near >= 0) { drag.current = near; event.currentTarget.setPointerCapture(event.pointerId) }
      else if (corners.length < 4) onCorners([...corners, next])
    }} onPointerMove={event => {
      if (drag.current === null || !editing) return
      onCorners(corners.map((p, i) => i === drag.current ? point(event) : p))
    }} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}>
      {corners.length >= 2 && <polygon points={corners.map(p => `${p.x * frame.width},${p.y * frame.height}`).join(' ')} fill="rgba(156,232,184,.035)" stroke="#b6f2c4" strokeWidth={2} strokeDasharray="7 6" vectorEffect="non-scaling-stroke" />}
      {editing && corners.map((p, i) => <g key={i} transform={`translate(${p.x * frame.width},${p.y * frame.height})`}>
        <circle r={frame.width * 0.008} fill="#b6f2c4" stroke="#133e36" strokeWidth={2} />
        <text x={frame.width * 0.014} y={-frame.width * 0.012} fill="#d9ffdf" fontSize={frame.width * 0.022} fontFamily="monospace" fontWeight="600">{['1', '2', '3', '4'][i]}</text>
      </g>)}
      {!editing && balls.map(ball => <g key={ball.id} onClick={() => onSelect(ball.id)} className="source-ball" transform={`translate(${ball.source_x * frame.width},${ball.source_y * frame.height})`}>
        <circle r={frame.width * 0.017} fill="transparent" stroke={selected === ball.id ? '#fff' : '#b6f2c4'} strokeWidth={selected === ball.id ? 3 : 1.5} vectorEffect="non-scaling-stroke" />
        {showLabels && <text x={frame.width * 0.020} y={-frame.width * 0.012} fill="#e0ffe4" fontSize={frame.width * 0.020} fontFamily="monospace">{String(ball.id).padStart(2, '0')}</text>}
      </g>)}
    </svg>
  </div>
}
