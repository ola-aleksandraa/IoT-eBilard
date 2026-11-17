import { ballColor } from './balls'
import type { BallKind, Point, TableBall, TableSnapshot } from './types'

// Placeholder table history: interpolates from a standard rack to the given layout.
// The backend has no history yet, so this only gives the timeline something to show.

const RACK_ROWS = [[1], [9, 2], [10, 8, 3], [11, 4, 12, 5], [6, 13, 7, 14, 15]]
const POCKET_EXITS: Point[] = [
  [0.02, 0.04],
  [0.5, 0.03],
  [0.98, 0.04],
  [0.02, 0.96],
  [0.5, 0.97],
  [0.98, 0.96],
]

const kindOf = (n: number): BallKind => (n === 0 ? 'cue' : n === 8 ? 'eight' : n > 8 ? 'striped' : 'solid')

/** Rack slots keyed by ball number (0 = cue ball on the head spot). Radius in table-height units. */
function rackSlots(r: number): Map<number, Point> {
  const dx = (r * Math.sqrt(3)) / 2 // 2r·cos30°, converted to table-width units (table is 2:1)
  const slots = new Map<number, Point>([[0, [0.25, 0.5]]])
  RACK_ROWS.forEach((row, k) =>
    row.forEach((n, j) => slots.set(n, [0.75 + k * dx, 0.5 + (j - (row.length - 1) / 2) * 2 * r])),
  )
  return slots
}

/**
 * Pushes overlapping balls apart (and back inside the cushions), in place.
 * Works in table-height units, where the 2:1 table spans x ∈ [0, 2].
 */
export function separateBalls(balls: TableBall[], iterations = 40): TableBall[] {
  const gap = 0.002
  const clamp = (b: TableBall) => {
    b.x = Math.min(Math.max(b.x, b.radius / 2), 1 - b.radius / 2)
    b.y = Math.min(Math.max(b.y, b.radius), 1 - b.radius)
  }
  for (let it = 0; it < iterations; it++) {
    let moved = false
    for (let i = 0; i < balls.length; i++) {
      for (let j = i + 1; j < balls.length; j++) {
        const a = balls[i]
        const b = balls[j]
        let dx = (b.x - a.x) * 2
        let dy = b.y - a.y
        let d = Math.hypot(dx, dy)
        const min = a.radius + b.radius + gap
        if (d >= min) continue
        if (d < 1e-6) {
          // Same spot: pick a deterministic direction.
          const angle = (a.id * 7 + b.id * 13) % 360 * (Math.PI / 180)
          ;[dx, dy, d] = [Math.cos(angle), Math.sin(angle), 1]
        }
        const push = (min - Math.hypot((b.x - a.x) * 2, b.y - a.y)) / 2
        const ux = dx / d
        const uy = dy / d
        a.x -= (ux * push) / 2
        a.y -= uy * push
        b.x += (ux * push) / 2
        b.y += uy * push
        moved = true
      }
    }
    balls.forEach(clamp)
    if (!moved) break
  }
  return balls
}

export function buildHistory(current: TableBall[], steps = 15): TableSnapshot[] {
  const r = current[0]?.radius ?? 0.026
  const slots = rackSlots(r)
  const free = new Set(slots.keys())
  const take = (n: number) => (free.delete(n) ? n : undefined)
  const firstFree = (kind: BallKind) => [...free].find((n) => kindOf(n) === kind) ?? [...free].find((n) => n !== 0)

  // Give every ball on the table a start slot: by number when known, otherwise by kind.
  // Unnumbered balls (backend data) also take the colour of their slot, so every ball looks distinct.
  const start = new Map<number, Point>()
  const placed = current.map((b): TableBall => {
    const n = (b.number != null ? take(b.number) : undefined) ?? take(firstFree(b.kind) ?? -1)
    start.set(b.id, n != null ? slots.get(n)! : [b.x, b.y])
    const color = b.number == null && b.color == null && n != null && n !== 0 && n !== 8 ? ballColor({ kind: kindOf(n), number: n }) : b.color
    return color ? { ...b, color } : b
  })

  // Remaining rack slots are balls potted during the frame.
  const numbered = current.some((b) => b.number != null)
  const potted = [...free].filter((n) => n !== 0)
  const pottedAt = new Map(potted.map((n, k) => [n, Math.round(((k + 1) * (steps - 1)) / (potted.length + 1))]))

  return Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1)
    const ease = 1 - (1 - t) ** 2
    const lerp = (a: Point, b: Point, seed: number): Point => {
      const wobble = i === 0 || i === steps - 1 ? 0 : Math.sin(i * 1.7 + seed) * 0.04 * (1 - t)
      return [a[0] + (b[0] - a[0]) * ease + wobble, a[1] + (b[1] - a[1]) * ease + wobble / 2]
    }
    const onTable = placed.map((b) => {
      const [x, y] = lerp(start.get(b.id)!, [b.x, b.y], b.id)
      return { ...b, x, y }
    })
    const leaving = potted
      .filter((n) => i < pottedAt.get(n)!)
      .map((n): TableBall => {
        const [x, y] = lerp(slots.get(n)!, POCKET_EXITS[n % 6], n)
        const look = { kind: kindOf(n), number: numbered ? n : undefined }
        return { id: 1000 + n, ...look, color: ballColor({ ...look, number: n }), x, y, radius: r }
      })
    return { id: `snap-${i}`, balls: separateBalls([...onTable, ...leaving]) }
  })
}
