import { useEffect, useRef } from 'react'
import { BALL_COLORS, type Ball } from './types'

export default function TableCanvas({ balls, ratio, selected, onSelect, showLabels, showGrid }: {
  balls: Ball[]; ratio: number; selected: number | null; onSelect: (id: number | null) => void; showLabels: boolean; showGrid: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  const geometry = useRef({ x: 0, y: 0, w: 1, h: 1 })
  useEffect(() => {
    const canvas = ref.current!
    const render = () => {
      const width = canvas.clientWidth, height = canvas.clientHeight
      const dpr = window.devicePixelRatio || 1
      canvas.width = width * dpr; canvas.height = height * dpr
      const ctx = canvas.getContext('2d')!
      ctx.scale(dpr, dpr)
      const w = Math.min(width - 66, (height - 74) * ratio), h = w / ratio
      const x = (width - w) / 2, y = (height - h) / 2
      geometry.current = { x, y, w, h }
      ctx.clearRect(0, 0, width, height)
      ctx.shadowColor = '#061f2440'; ctx.shadowBlur = 22; ctx.shadowOffsetY = 8
      ctx.fillStyle = '#344745'; ctx.beginPath(); ctx.roundRect(x - 19, y - 19, w + 38, h + 38, 13); ctx.fill()
      ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0
      ctx.strokeStyle = '#63736b'; ctx.lineWidth = 1; ctx.stroke()
      ctx.fillStyle = '#236761'; ctx.fillRect(x - 7, y - 7, w + 14, h + 14)
      const gradient = ctx.createLinearGradient(x, y, x + w, y + h)
      gradient.addColorStop(0, '#358b80'); gradient.addColorStop(1, '#267c73')
      ctx.fillStyle = gradient; ctx.fillRect(x, y, w, h)
      ctx.strokeStyle = '#144e47'; ctx.strokeRect(x, y, w, h)
      if (showGrid) {
        ctx.strokeStyle = '#d6f5e919'; ctx.lineWidth = 1
        for (let i = 1; i < 8; i++) { ctx.beginPath(); ctx.moveTo(x + w * i / 8, y); ctx.lineTo(x + w * i / 8, y + h); ctx.stroke() }
        for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo(x, y + h * i / 4); ctx.lineTo(x + w, y + h * i / 4); ctx.stroke() }
        ctx.setLineDash([4, 4]); ctx.strokeStyle = '#d6f5e935'; ctx.beginPath(); ctx.arc(x + w / 4, y + h / 2, h * 0.18, -Math.PI / 2, Math.PI / 2); ctx.stroke(); ctx.setLineDash([])
      }
      ctx.fillStyle = '#0c302d'
      for (const [px, py] of [[x, y], [x + w / 2, y - 2], [x + w, y], [x, y + h], [x + w / 2, y + h + 2], [x + w, y + h]]) {
        ctx.beginPath(); ctx.arc(px, py, Math.max(6, h * 0.045), 0, Math.PI * 2); ctx.fill()
      }
      ctx.fillStyle = '#adbfad'
      for (const fraction of [1 / 8, 2 / 8, 3 / 8, 5 / 8, 6 / 8, 7 / 8]) {
        for (const py of [y - 13, y + h + 13]) { ctx.beginPath(); ctx.arc(x + w * fraction, py, 1.5, 0, Math.PI * 2); ctx.fill() }
      }
      ctx.font = '10px ui-monospace, monospace'; ctx.fillStyle = '#7b8b86'
      ctx.fillText('0, 0', x - 8, y - 28); ctx.textAlign = 'right'; ctx.fillText('1, 1', x + w + 7, y + h + 34); ctx.textAlign = 'left'
      for (const ball of balls) {
        const bx = x + ball.x * w, by = y + ball.y * h, r = Math.max(4, ball.radius * h)
        ctx.save()
        if (selected === ball.id) { ctx.strokeStyle = '#caff94'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(bx, by, r + 5, 0, Math.PI * 2); ctx.stroke() }
        ctx.shadowColor = '#092a3388'; ctx.shadowBlur = 4; ctx.shadowOffsetY = 2
        ctx.beginPath(); ctx.arc(bx, by, r, 0, Math.PI * 2); ctx.fillStyle = ball.kind === 'striped' ? '#f0eee5' : BALL_COLORS[ball.kind]; ctx.fill()
        ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0
        ctx.clip()
        if (ball.kind === 'striped') { ctx.fillStyle = BALL_COLORS[ball.kind]; ctx.fillRect(bx - r, by - r * 0.44, r * 2, r * 0.88) }
        const shine = ctx.createRadialGradient(bx - r * 0.35, by - r * 0.45, 0, bx, by, r * 1.2)
        shine.addColorStop(0, '#ffffff65'); shine.addColorStop(0.4, '#ffffff00'); shine.addColorStop(1, '#00000040')
        ctx.fillStyle = shine; ctx.fillRect(bx - r, by - r, r * 2, r * 2)
        if (ball.kind === 'unknown') { ctx.fillStyle = '#fff'; ctx.font = `bold ${r * 1.5}px sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('?', bx, by) }
        ctx.restore()
        if (showLabels) {
          ctx.fillStyle = '#edfff3'; ctx.font = '600 10px ui-monospace, monospace'; ctx.textAlign = 'center'
          ctx.fillText(String(ball.id).padStart(2, '0'), bx, by - r - 6); ctx.textAlign = 'left'
        }
      }
    }
    const observer = new ResizeObserver(render); observer.observe(canvas); render()
    return () => observer.disconnect()
  }, [balls, ratio, selected, showLabels, showGrid])
  return <canvas ref={ref} tabIndex={0} aria-label={`Virtual table with ${balls.length} detected balls. Use arrow keys to inspect balls; Escape clears selection.`} onKeyDown={event => {
    if (event.key === 'Escape') onSelect(null)
    if (['ArrowLeft', 'ArrowRight'].includes(event.key) && balls.length) {
      event.preventDefault()
      const index = balls.findIndex(ball => ball.id === selected)
      const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + balls.length) % balls.length
      onSelect(balls[next].id)
    }
  }} onClick={event => {
    const bounds = event.currentTarget.getBoundingClientRect(), { x, y, w, h } = geometry.current
    const px = event.clientX - bounds.left, py = event.clientY - bounds.top
    const hit = balls.find(ball => Math.hypot(px - x - ball.x * w, py - y - ball.y * h) < Math.max(12, ball.radius * h + 5))
    onSelect(hit?.id ?? null)
  }} />
}
