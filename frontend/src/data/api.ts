// Minimal client for both backends (FastAPI, /api/v1):
//   /api/v1    → website backend (back_website/, :8001) – shot planning
//   /pi/api/v1 → Raspberry Pi backend (back_raspberry/, :8002) – camera capture + ball detection
// Vite proxies both prefixes. Response types are the subset of back_website/app/schemas.py
// and back_raspberry/app/schemas.py this UI reads.
import type { BallKind, PocketIndex, Point, ShotSuggestion, TableBall } from './types'

const API = '/api/v1'
const PI_API = '/pi/api/v1'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`)
    this.status = status
  }
}

interface ApiBall {
  id: number
  kind: BallKind
  x: number
  y: number
  radius: number
  confidence: number
}

interface AnalysisResult {
  table_status: 'detected' | 'searching'
  detection: { balls: ApiBall[] } | null
}

interface ApiShot {
  target_ball_id: number
  pocket: number
  cue_path: Point[]
  target_path: Point[]
  ghost_pos: Point | null
}

interface ShotsResult {
  status: 'ok' | 'no_cue_ball' | 'multiple_cue_balls' | 'no_targets'
  shots: ApiShot[]
}

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

/** Raspberry Pi: POST /camera/detect – the Pi captures a frame itself; returns balls in table coordinates. */
export async function detectCamera(signal?: AbortSignal): Promise<TableBall[]> {
  const result = await request<AnalysisResult>(`${PI_API}/camera/detect`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({}),
    signal,
  })
  if (result.table_status !== 'detected' || !result.detection) throw new ApiError(422, 'table not detected')
  return result.detection.balls.map(({ id, kind, x, y, radius }) => ({ id, kind, x, y, radius }))
}

/** POST /shots – best suggested shot for a layout, or null when there is none. */
export async function suggestShot(balls: TableBall[], signal?: AbortSignal): Promise<ShotSuggestion | null> {
  const result = await request<ShotsResult>(`${API}/shots`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ balls: balls.map(({ id, kind, x, y, radius }) => ({ id, kind, x, y, radius })), top_n: 1 }),
    signal,
  })
  const shot = result.status === 'ok' ? result.shots[0] : undefined
  if (!shot) return null
  return {
    target_ball_id: shot.target_ball_id,
    pocket: shot.pocket as PocketIndex,
    cue_path: shot.cue_path,
    target_path: shot.target_path,
    ghost_pos: shot.ghost_pos,
  }
}
