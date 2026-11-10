// Domain types for the table view.
//
// Ball / shot shapes intentionally mirror the backend contract
// (back_raspberry/app/schemas.py: Ball; back_website/app/schemas.py: ShotBall, Shot) so live data can be dropped in:
// coordinates are 0..1 of the playing surface, origin top-left, y pointing down,
// radius is a fraction of the table height.

export type BallKind = 'cue' | 'eight' | 'solid' | 'striped' | 'unknown'

export type Point = [x: number, y: number]

export interface BallLook {
  kind: BallKind
  /** Ball number. The backend only classifies kinds, so this is optional. */
  number?: number
  /** Overrides the colour derived from `number`. */
  color?: string
}

export interface TableBall extends BallLook {
  id: number
  x: number
  y: number
  radius: number
}

/** Pocket index as used by the backend: TL, TM, TR, BL, BM, BR. */
export type PocketIndex = 0 | 1 | 2 | 3 | 4 | 5

export interface ShotSuggestion {
  target_ball_id: number
  pocket: PocketIndex
  cue_path: Point[]
  target_path: Point[]
  ghost_pos: Point | null
}

export interface TableSnapshot {
  id: string
  balls: TableBall[]
}

export interface Player {
  id: string
  name: string
  initials: string
  score: number
  /** Ball shown next to the score (the player's group). */
  badge: BallLook
}

export interface PlayerStat {
  label: string
  value: string
  hint: string
}

/** Cue tip contact point on the cue-ball face, both axes in -1..1 of the radius. */
export interface HitPoint {
  x: number
  y: number
}
