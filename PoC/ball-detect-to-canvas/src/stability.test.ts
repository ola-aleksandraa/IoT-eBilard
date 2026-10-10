import { describe, expect, it } from 'vitest'
import { BallStabilizer, CornerConsensus } from './stability'
import type { Ball, Calibration, Detection } from './types'

const calibration: Calibration = { image_width: 1280, image_height: 720, corners: [{ x: .1, y: .1 }, { x: .9, y: .1 }, { x: .95, y: .9 }, { x: .05, y: .9 }] }
const shifted = (delta: number): Calibration => ({ ...calibration, corners: calibration.corners.map(p => ({ x: p.x + delta, y: p.y + delta })) })
const ball = (x = .3, y = .4, id = 1): Ball => ({ id, kind: 'solid', x, y, radius: .026, source_x: x, source_y: y, color: '#ff0000', confidence: .8, reason: '', white_fraction: .1, method: 'contour' })
const frame = (balls: Ball[]): Detection => ({ balls, table: { width: 1000, height: 500, ratio: 2 }, cloth_hue: 80, processing_ms: 20, images: null, homography: [], warnings: [], coordinate_system: 'normalized' })

describe('fixed-camera calibration', () => {
  it('requires eight observations and returns the robust center of their corners', () => {
    const c = new CornerConsensus()
    for (const delta of [-.002, .001, .002, -.001, 0, -.001, .001]) expect(c.add(shifted(delta))).toBeNull()
    const locked = c.add(calibration)!
    expect(locked.corners[0].x).toBeCloseTo(.1, 6)
    expect(locked.corners[0].y).toBeCloseTo(.1, 6)
  })
  it('rejects isolated outliers and does not lock during camera movement', () => {
    const c = new CornerConsensus()
    for (let i = 0; i < 12; i++) expect(c.add(shifted(i * .01))).toBeNull()
    c.reset()
    for (let i = 0; i < 5; i++) expect(c.add(calibration)).toBeNull()
    expect(c.add(shifted(.08))).toBeNull()
    expect(c.add(calibration)).toBeNull(); expect(c.add(calibration)).toBeNull()
    expect(c.add(calibration)?.corners).toEqual(calibration.corners)
  })
  it('starts over after resolution changes or explicit recalibration', () => {
    const c = new CornerConsensus()
    for (let i = 0; i < 7; i++) c.add(calibration)
    expect(c.add({ ...calibration, image_width: 640 })).toBeNull()
    expect(c.progress).toBe(1)
    c.reset(); expect(c.progress).toBe(0)
  })
})

describe('stationary-ball stabilization', () => {
  it('keeps exact displayed positions through detector jitter and input reordering', () => {
    const s = new BallStabilizer()
    const original = s.update(frame([ball(.3), ball(.7, .6, 2)]), .006).balls
    for (const delta of [.001, -.002, .0008, -.0015]) {
      const next = s.update(frame([ball(.7 + delta, .6, 1), ball(.3 + delta, .4, 2)]), .006).balls
      expect(next).toEqual(original)
    }
  })
  it('moves a ball immediately for a significant displacement', () => {
    const s = new BallStabilizer(); const initial = s.update(frame([ball()]), .006).balls[0]
    const moved = s.update(frame([ball(.33)]), .006).balls[0]
    expect(moved.id).toBe(initial.id); expect(moved.x).toBe(.33)
  })
  it('suppresses isolated modest noise but accepts repeated displacement', () => {
    const s = new BallStabilizer(); s.update(frame([ball()]), .006)
    expect(s.update(frame([ball(.305)]), .006).balls[0].x).toBe(.3)
    expect(s.update(frame([ball(.3005)]), .006).balls[0].x).toBe(.3)
    s.update(frame([ball(.305)]), .006)
    expect(s.update(frame([ball(.305)]), .006).balls[0].x).toBe(.305)
  })
  it('does not freeze accumulated slow rolling forever', () => {
    const s = new BallStabilizer(); s.update(frame([ball()]), .006)
    let result = frame([])
    for (let i = 1; i <= 20; i++) result = s.update(frame([ball(.3 + i * .001)]), .006)
    expect(result.balls[0].x).toBeGreaterThan(.315)
  })
  it('bridges two missed detections but removes a ball after three', () => {
    const s = new BallStabilizer(); s.update(frame([ball()]), .006)
    expect(s.update(frame([]), .006).balls).toHaveLength(1)
    expect(s.update(frame([]), .006).balls).toHaveLength(1)
    expect(s.update(frame([]), .006).balls).toHaveLength(0)
  })
  it('requires two observations for newly appearing candidates', () => {
    const s = new BallStabilizer(); s.update(frame([ball()]), .006)
    expect(s.update(frame([ball(), ball(.8)]), .006).balls).toHaveLength(1)
    expect(s.update(frame([ball(), ball(.8)]), .006).balls).toHaveLength(2)
  })
  it('does not flicker ball types for one ambiguous observation', () => {
    const s = new BallStabilizer(); s.update(frame([ball()]), .006)
    const ambiguous = frame([{ ...ball(), kind: 'striped' }])
    expect(s.update(ambiguous, .006).balls[0].kind).toBe('solid')
    expect(s.update(ambiguous, .006).balls[0].kind).toBe('solid')
    expect(s.update(ambiguous, .006).balls[0].kind).toBe('striped')
  })
})
