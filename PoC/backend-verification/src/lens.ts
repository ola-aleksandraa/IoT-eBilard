import type { LensCalibration, Point } from './types'

// OpenCV's radial/tangential projection. Automatic table calibration emits k1
// only; source/table geometry stays in corrected pixels throughout the API.
function distort(x: number, y: number, lens: LensCalibration) {
  const [k1 = 0, k2 = 0, p1 = 0, p2 = 0, k3 = 0] = lens.distortion
  const r2 = x * x + y * y, radial = 1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3
  return { x: x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x),
    y: y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y }
}

/** Corrected normalized source coordinates → the original camera image. */
export function rawPoint(point: Point, lens?: LensCalibration | null): Point {
  if (!lens) return point
  const k = lens.camera_matrix, w = lens.image_width - 1, h = lens.image_height - 1
  const p = distort((point.x * w - k[0][2]) / k[0][0], (point.y * h - k[1][2]) / k[1][1], lens)
  return { x: (p.x * k[0][0] + k[0][2]) / w, y: (p.y * k[1][1] + k[1][2]) / h }
}

/** Manual clicks are made on the original image; retain corrected corners. */
export function correctedPoint(point: Point, lens?: LensCalibration | null): Point {
  if (!lens) return point
  const k = lens.camera_matrix, w = lens.image_width - 1, h = lens.image_height - 1
  const xd = (point.x * w - k[0][2]) / k[0][0], yd = (point.y * h - k[1][2]) / k[1][1]
  let x = xd, y = yd
  for (let i = 0; i < 60; i++) {
    const p = distort(x, y, lens)
    // Pixels outside the retained corrected canvas have no editable source
    // coordinate. Clamp each step so clicks there cannot diverge to NaN.
    x = Math.max(-k[0][2] / k[0][0], Math.min((w - k[0][2]) / k[0][0], x + xd - p.x))
    y = Math.max(-k[1][2] / k[1][1], Math.min((h - k[1][2]) / k[1][1], y + yd - p.y))
  }
  return { x: Math.max(0, Math.min(1, (x * k[0][0] + k[0][2]) / w)),
    y: Math.max(0, Math.min(1, (y * k[1][1] + k[1][2]) / h)) }
}

/** A straight corrected cushion appears curved on the original camera frame. */
export function rawOutline(corners: Point[], lens?: LensCalibration | null): Point[] {
  if (!lens || corners.length !== 4) return corners
  return corners.flatMap((a, i) => Array.from({ length: 24 }, (_, j) => {
    const b = corners[(i + 1) % 4], t = j / 24
    return rawPoint({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }, lens)
  }))
}
