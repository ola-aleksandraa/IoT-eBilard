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
