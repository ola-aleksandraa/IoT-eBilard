export type Point = { x: number; y: number }
export type Calibration = { corners: Point[]; image_width: number; image_height: number }
export type Settings = {
  table_ratio: number; ball_radius_ratio: number; cloth_hue: number | null;
  hue_tolerance: number; saturation_min: number; split_touching: boolean;
}
export type Ball = {
  id: number; kind: 'cue' | 'eight' | 'solid' | 'striped' | 'unknown';
  x: number; y: number; radius: number; source_x: number; source_y: number;
  confidence: number; reason: string; white_fraction: number; method: string;
}
// Presentation belongs entirely to this client, not to the recognition API.
export const BALL_COLORS: Record<Ball['kind'], string> = { cue: '#faf8ef', eight: '#202429', solid: '#e3ad48', striped: '#e3ad48', unknown: '#87949c' }
export const BALL_NAMES: Record<Ball['kind'], string> = { cue: 'White', eight: 'Black', solid: 'Full', striped: 'Half', unknown: 'Unknown' }
export const DEFAULT_SETTINGS: Settings = { table_ratio: 2, ball_radius_ratio: .026, cloth_hue: null, hue_tolerance: 16, saturation_min: 55, split_touching: true }
export type Geometry = {
  table_ratio: number; source_to_table: number[][]; table_to_source: number[][];
  origin: 'top_left'; x_direction: 'right'; y_direction: 'down'; center_unit: 'normalized_table';
  radius_unit: 'table_height'; source_space: 'oriented_pixels' | 'undistorted_oriented_pixels';
}
export type Counts = Record<Ball['kind'] | 'total', number>
export type Detection = { balls: Ball[]; counts: Counts; geometry: Geometry; cloth_hue: number | null; processing_ms: number; warnings: string[] }
export type AnalysisResult = {
  schema_version: '1.0'; frame_id: string; client_frame_id: string | null;
  table_status: 'detected' | 'searching'; source: { kind: 'upload' | 'camera'; width: number; height: number; acquired_at: string; lens_corrected: boolean };
  calibration: Calibration | null; settings: Settings; detection: Detection | null; analysis_ms: number;
}
export type Frame = { image: string; width: number; height: number; name: string; synthetic: boolean }

export type Shot = {
  target_ball_id: number; pocket: number; shot_type: 'direct' | 'bank'; score: number; cut_angle: number
  is_blocked: boolean; blocked_reason: string | null; velocity_remaining: number
  cue_path: [number, number][]; target_path: [number, number][]; cue_deflect_path: [number, number][]
  ghost_pos: [number, number] | null; bank_point: [number, number] | null
}
export type ShotsResponse = { status: 'ok' | 'no_cue_ball' | 'multiple_cue_balls' | 'no_targets'; cue_ball_id: number | null; shots: Shot[]; blocked: Shot[] }
export const POCKET_NAMES = ['top left', 'top middle', 'top right', 'bottom left', 'bottom middle', 'bottom right']
export const SHOT_MESSAGES: Record<Exclude<ShotsResponse['status'], 'ok'> | 'invalid_aim', string> = {
  no_cue_ball: 'No white ball detected, so no shots to predict.',
  multiple_cue_balls: 'More than one white ball detected, so no shots to predict.',
  no_targets: 'No other balls on the table.',
  invalid_aim: 'Aim point is inside the white ball.',
}
// Live cue-stick prediction: full physics roll-out (motion, not just pocket lines).
export type MotionEvent = {
  t: number; type: 'contact' | 'cushion' | 'pot'; ball: number; with?: number; pocket?: number
  x?: number; y?: number; cut_angle?: number
}
export type MotionBall = { id: number; path: [number, number][]; potted_t: number | null }
export type MotionPrediction = {
  status: 'ok' | 'no_cue_ball' | 'multiple_cue_balls' | 'no_targets' | 'invalid_aim'
  cue_ball_id: number | null; first_ball_id: number | null
  ghost_pos: [number, number] | null; cut_angle: number | null
  power: number; duration: number; dt: number
  balls: MotionBall[]; events: MotionEvent[]; potted: number[]
}

export function downloadJSON(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
