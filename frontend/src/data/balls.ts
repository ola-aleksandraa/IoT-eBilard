import type { BallLook } from './types'

const BALL_COLORS: Record<number, string> = {
  1: '#f2c30e',
  2: '#1e5ac4',
  3: '#d8322c',
  4: '#6b3aa0',
  5: '#ee7a1e',
  6: '#1a7a3e',
  7: '#7c2420',
  8: '#16181c',
}

export const IVORY = '#f7f4ec'
const UNKNOWN_COLOR = '#9aa8b8'
// The backend only classifies kinds (no numbers), so unnumbered balls get a colour per group.
const GROUP_COLOR = { solid: '#d8322c', striped: '#1e5ac4' } as const

/** Colour of the solid body (solids, eight) or of the stripe (striped balls). */
export function ballColor(ball: BallLook): string {
  if (ball.color) return ball.color
  if (ball.kind === 'cue') return IVORY
  if (ball.kind === 'eight') return BALL_COLORS[8]
  if (ball.number != null) return BALL_COLORS[((ball.number - 1) % 8) + 1] ?? UNKNOWN_COLOR
  if (ball.kind === 'solid' || ball.kind === 'striped') return GROUP_COLOR[ball.kind]
  return UNKNOWN_COLOR
}
