import { type Ball, type Calibration, type Detection } from './types'

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

/** Eight consistent observations, robust to two isolated corner outliers.
 * Lock only on temporal agreement. It does not establish absolute accuracy.
 */
export class CornerConsensus {
  private samples: Calibration[] = []
  private accepted = 0
  readonly target = 8
  reset() { this.samples = []; this.accepted = 0 }
  get progress() { return this.accepted }
  add(value: Calibration): Calibration | null {
    const previous = this.samples[0]
    if (previous && (previous.image_width !== value.image_width || previous.image_height !== value.image_height)) this.reset()
    this.samples.push(structuredClone(value))
    this.samples = this.samples.slice(-12)
    const aggregate = (samples: Calibration[]) => ({ ...value, corners: value.corners.map((_, i) => ({ x: median(samples.map(s => s.corners[i].x)), y: median(samples.map(s => s.corners[i].y)) })) })
    const center = aggregate(this.samples)
    const diagonal = Math.hypot(value.image_width, value.image_height)
    const inliers = this.samples.filter(sample => sample.corners.every((p, i) => Math.hypot((p.x - center.corners[i].x) * value.image_width, (p.y - center.corners[i].y) * value.image_height) / diagonal <= 0.004))
    // Consecutive recent agreement avoids locking just after the camera moves.
    const recentStable = this.samples.slice(-3).every(sample => inliers.includes(sample))
    this.accepted = Math.min(inliers.length, recentStable ? this.target : this.target - 1)
    if (inliers.length < this.target || !recentStable) return null
    return aggregate(inliers)
  }
}

type Track = { ball: Ball; misses: number; hits: number; pending: Ball | null; appearance: Ball['kind'] | null; appearanceHits: number }
const distance = (a: Ball, b: Ball, ratio: number) => Math.hypot((a.x - b.x) * ratio, a.y - b.y)

/** Display stabilization, not physics tracking or printed-number identification. */
export class BallStabilizer {
  private tracks: Track[] = []
  private nextId = 1
  private initialized = false
  reset() { this.tracks = []; this.nextId = 1; this.initialized = false }

  update(detection: Detection, deadband: number): Detection {
    const ratio = detection.geometry.table_ratio
    const pairs = this.tracks.flatMap((track, index) => detection.balls.map((ball, candidate) => {
      const d = distance(track.ball, ball, ratio)
      const distinctive = ['cue', 'eight'].includes(track.ball.kind) && ball.kind !== track.ball.kind && ball.kind !== 'unknown'
      return { index, candidate, distance: d, cost: d + (distinctive ? 0.12 : 0) }
    })).filter(pair => pair.distance < 0.35).sort((a, b) => a.cost - b.cost)
    const usedTracks = new Set<number>(), usedBalls = new Set<number>()
    for (const pair of pairs) {
      if (usedTracks.has(pair.index) || usedBalls.has(pair.candidate)) continue
      usedTracks.add(pair.index); usedBalls.add(pair.candidate)
      const track = this.tracks[pair.index], observed = detection.balls[pair.candidate]
      track.hits++; track.misses = 0
      if (observed.kind === track.ball.kind) { track.appearance = null; track.appearanceHits = 0 }
      else {
        track.appearanceHits = track.appearance === observed.kind ? track.appearanceHits + 1 : 1
        track.appearance = observed.kind
        if (track.appearanceHits >= 3) {
          track.ball = { ...track.ball, kind: observed.kind, confidence: observed.confidence, reason: observed.reason }
          track.appearanceHits = 0
        }
      }
      const movement = distance(track.ball, observed, ratio)
      // Compare with the DISPLAYED anchor, so slow real motion accumulates.
      if (movement <= deadband) { track.pending = null; continue }
      const confirmed = track.pending && distance(track.pending, observed, ratio) <= deadband
      if (movement > deadband * 3 || confirmed) {
        const position = confirmed && movement <= deadband * 3 ? {
          x: (track.pending!.x + observed.x) / 2, y: (track.pending!.y + observed.y) / 2,
          source_x: (track.pending!.source_x + observed.source_x) / 2, source_y: (track.pending!.source_y + observed.source_y) / 2,
        } : { x: observed.x, y: observed.y, source_x: observed.source_x, source_y: observed.source_y }
        track.ball = { ...track.ball, ...position }
        track.pending = null
      } else track.pending = observed
    }
    this.tracks.forEach((track, i) => { if (!usedTracks.has(i)) { track.misses++; track.pending = null; track.appearanceHits = 0 } })
    // Short detector dropouts do not make stationary balls blink. Three missed
    // frames (~1.5 s) remove a pocketed/occluded ball; new candidates need two.
    this.tracks = this.tracks.filter(track => track.misses < 3 && !(track.hits < 2 && track.misses > 0))
    detection.balls.forEach((ball, i) => {
      if (!usedBalls.has(i)) this.tracks.push({ ball: { ...ball, id: this.nextId++ }, misses: 0, hits: this.initialized ? 1 : 2, pending: null, appearance: null, appearanceHits: 0 })
    })
    this.initialized = true
    // Hysteresis and dropout retention must not display two cue/eight balls.
    // Demote the weaker display claim, keeping the position visible as unknown.
    const visible = this.tracks.filter(track => track.hits >= 2)
    const displayed = visible.map(track => ({ ...track.ball }))
    for (const kind of ['cue', 'eight'] as const) {
      const candidates = visible.map((track, index) => ({ track, index })).filter(({ track }) => track.ball.kind === kind)
      candidates.sort((a, b) => a.track.misses - b.track.misses || b.track.ball.confidence - a.track.ball.confidence)
      for (const { index } of candidates.slice(1)) {
        displayed[index] = { ...displayed[index], kind: 'unknown', confidence: .35, reason: 'Special-ball identity is uncertain while the layout settles.' }
      }
    }
    return { ...detection, balls: displayed, counts: {
      total: displayed.length, cue: 0, eight: 0, solid: 0, striped: 0, unknown: 0,
      ...Object.fromEntries(['cue', 'eight', 'solid', 'striped', 'unknown'].map(kind => [kind, displayed.filter(ball => ball.kind === kind).length])),
    } }
  }
}
