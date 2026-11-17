/** Max tip offset from the centre (fraction of the radius) before a miscue. */
export const MISCUE_LIMIT = 0.76

export type SpinZone = 'naciag' | 'stop' | 'sruba'

export function spinZone(v: number): SpinZone {
  if (v >= 0.15) return 'naciag'
  if (v <= -0.15) return 'sruba'
  return 'stop'
}

const FRACTIONS: Record<number, string> = { 0.25: '1/4', 0.5: '1/2', 0.75: '3/4', 1: '1' }

/** "+1/2 R", "−1/4 R", "0 R" – vertical offset rounded to quarters of the radius. */
export function formatOffset(v: number): string {
  const q = Math.round(v * 4) / 4
  if (q === 0) return '0 R'
  return `${q > 0 ? '+' : '−'}${FRACTIONS[Math.abs(q)]} R`
}
