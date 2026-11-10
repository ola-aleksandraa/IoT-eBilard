import { css, cx } from '../../styled-system/css'
import type { Player } from '../data/types'
import { BallIcon } from './Ball'
import { Avatar, Card, Eyebrow } from './ui'

export function PlayersCard({ players, activeId }: { players: Player[]; activeId: string }) {
  return (
    <Card label="Gracze w sesji" className={css({ px: '16px', pt: '20px', pb: '16px' })}>
      <Eyebrow className={css({ px: '4px' })}>Gracze w sesji</Eyebrow>
      <ul className={css({ display: 'flex', flexDirection: 'column', gap: '6px', mt: '14px' })}>
        {players.map((p) => {
          const active = p.id === activeId
          return (
            <li
              key={p.id}
              aria-current={active ? 'true' : undefined}
              className={cx(
                css({
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  h: '64px',
                  p: '12px',
                  borderRadius: '10px',
                  border: '1px solid',
                }),
                active ? css({ bg: 'accentSoft', borderColor: 'accent' }) : css({ bg: 'sunken', borderColor: 'line' }),
              )}
            >
              <Avatar initials={p.initials} size={38} tone={active ? 'accent' : 'neutral'} />
              <span className={css({ textStyle: 'name', color: 'text', flex: 1, minW: 0, truncate: true })}>{p.name}</span>
              <span className={css({ display: 'flex', alignItems: 'center', gap: '7px', ml: '-6px', flexShrink: 0 })}>
                <span
                  className={cx(css({ textStyle: 'stat', lineHeight: '29px' }), active ? css({ color: 'accent' }) : css({ color: 'textSubtle' }))}
                  aria-label={`Wynik: ${p.score}`}
                >
                  {p.score}
                </span>
                <BallIcon ball={p.badge} size={40} />
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
