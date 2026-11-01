import { expect, it } from 'vitest'
import { correctedPoint, rawOutline, rawPoint } from './lens'
import type { LensCalibration } from './types'

const lens: LensCalibration = { image_width: 1000, image_height: 500,
  camera_matrix: [[1000, 0, 500], [0, 1000, 250], [0, 0, 1]], distortion: [-.4, 0, 0, 0, 0] }

it('overlays corrected detections on known distorted camera pixels', () => {
  const p = rawPoint({ x: 300 / 999, y: 150 / 499 }, lens)
  expect(p.x).toBeCloseTo(304 / 999, 10)
  expect(p.y).toBeCloseTo(152 / 499, 10)
  expect(rawPoint({ x: .2, y: .3 })).toEqual({ x: .2, y: .3 })
})

it('maps manual clicks back to corrected coordinates without double correction', () => {
  for (const p of [{ x: .15, y: .12 }, { x: .8, y: .85 }, { x: .5, y: .5 }]) {
    const corrected = correctedPoint(rawPoint(p, lens), lens)
    expect(corrected.x).toBeCloseTo(p.x, 6)
    expect(corrected.y).toBeCloseTo(p.y, 6)
  }
  const outside = correctedPoint({ x: 0, y: 0 }, { ...lens, distortion: [-.7, 0, 0, 0, 0] })
  expect(outside).toEqual({ x: 0, y: 0 })
})

it('curves raw-camera rail overlays rather than drawing a misleading straight chord', () => {
  const outline = rawOutline([{ x: .1, y: .1 }, { x: .9, y: .1 }, { x: .9, y: .9 }, { x: .1, y: .9 }], lens)
  expect(outline).toHaveLength(96)
  expect(outline[12].y).toBeLessThan((outline[0].y + outline[24].y) / 2)
})
