export type Point = { x: number; y: number }
export type Calibration = { corners: Point[]; image_width: number; image_height: number }
export type Settings = {
  table_ratio: number; ball_radius_ratio: number; cloth_hue: number | null;
  hue_tolerance: number; saturation_min: number; split_touching: boolean;
}
export type Ball = {
  id: number; kind: 'cue' | 'eight' | 'solid' | 'striped' | 'unknown';
  x: number; y: number; radius: number; source_x: number; source_y: number;
  color: string; confidence: number; reason: string; white_fraction: number; method: string;
}
// Color encodes type only; individual pool-ball hues are deliberately ignored.
export const BALL_COLORS: Record<Ball['kind'], string> = { cue: '#faf8ef', eight: '#202429', solid: '#e3ad48', striped: '#e3ad48', unknown: '#87949c' }
export const BALL_NAMES: Record<Ball['kind'], string> = { cue: 'White', eight: 'Black', solid: 'Full', striped: 'Half', unknown: 'Unknown' }

export type Detection = {
  balls: Ball[]; table: { width: number; height: number; ratio: number };
  cloth_hue: number | null; processing_ms: number; warnings: string[];
  images: { rectified: string; mask: string; overlay: string } | null;
  homography: number[][]; coordinate_system: string;
}
export type Frame = { image: string; width: number; height: number; name: string; synthetic: boolean; lens_corrected?: boolean }
export type LiveResponse = { table_status: 'searching' | 'detected'; calibration: Calibration | null; detection: Detection | null }
export const DEFAULT_SETTINGS: Settings = { table_ratio: 2, ball_radius_ratio: 0.026, cloth_hue: null, hue_tolerance: 16, saturation_min: 55, split_touching: true }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(`/api${path}`, { ...init, signal: init?.signal ?? AbortSignal.timeout(60000) }) }
  catch { throw new Error('Cannot reach the detection service. Start FastAPI on port 8000, then try again.') }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Detection service returned ${response.status}. Check that FastAPI is running.`)
  }
  return response.json() as Promise<T>
}

export async function imageBlob(url: string) { return (await fetch(url)).blob() }

export function downloadJSON(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
