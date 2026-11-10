// Placeholder data reproducing the Figma mock-up. Used when the backend is not reachable
// and for everything the backend does not provide yet (players, score, turn, stats).
import { buildHistory } from './history'
import type { Player, PlayerStat, Point, ShotSuggestion, TableBall, TableSnapshot } from './types'

const R = 15 / 420 // ball radius as a fraction of the table height (30px ball on a 420px felt)

type Spec = [number: number, x: number, y: number]

function toBall([number, x, y]: Spec, id: number): TableBall {
  const kind = number === 0 ? 'cue' : number === 8 ? 'eight' : number > 8 ? 'striped' : 'solid'
  return { id, kind, number: number === 0 ? undefined : number, x, y, radius: R }
}

/** Current layout from the design (positions measured on the 840×420 felt). */
const CURRENT: Spec[] = [
  [0, 0.1917, 0.5595],
  [1, 0.5512, 0.3],
  [2, 0.8917, 0.5],
  [3, 0.6917, 0.6405],
  [5, 0.4321, 0.7595],
  [8, 0.5119, 0.4595],
  [9, 0.7917, 0.3405],
  [11, 0.8714, 0.7],
  [12, 0.3321, 0.2],
  [14, 0.6321, 0.8595],
]

/** Ball layout from the design. */
export const mockBalls: TableBall[] = CURRENT.map(toBall)

export const history: TableSnapshot[] = buildHistory(mockBalls)

const idOf = (n: number) => mockBalls.find((b) => b.number === n)!.id

const cue: Point = [0.1917, 0.5595]
const three: Point = [0.6917, 0.6405]
const five: Point = [0.4321, 0.7595]

/** Predicted path for the current aim (drawn on the table in the design): cue → 3 → bottom-right. */
export const predictedShot: ShotSuggestion = {
  target_ball_id: idOf(3),
  pocket: 5,
  cue_path: [cue, three],
  target_path: [three, [0.9917, 1]],
  ghost_pos: three,
}

/** Suggestion revealed by "Pomóż mi": cut the 5 into the bottom-middle pocket. */
export const hintShot: ShotSuggestion = {
  target_ball_id: idOf(5),
  pocket: 4,
  cue_path: [cue, [0.4143, 0.6976]],
  target_path: [five, [0.5, 1]],
  ghost_pos: [0.4143, 0.6976],
}

export const session = {
  players: [
    { id: 'artur', name: 'Artur W.', initials: 'AW', score: 4, badge: { kind: 'eight', number: 8 } },
    {
      id: 'wojtek',
      name: 'Wojtek K.',
      initials: 'WK',
      score: 3,
      badge: { kind: 'striped', number: 9, color: '#d8322c' },
    },
  ] satisfies Player[],
  activePlayerId: 'artur',
  round: 12,
  hintsLeft: 2,
  hintsTotal: 3,
  turnStartedSecondsAgo: 42,
  me: { name: 'Artur W.', initials: 'AW', level: 'Średnio zaawansowany' },
}

export const stats: PlayerStat[] = [
  { label: 'Celność', value: '68%', hint: 'Rywal 67%' },
  { label: 'Pozostało', value: '4 bile', hint: 'Rywal: 3' },
]

export const averageTurn = '01:10'
