import { css } from '../../styled-system/css'
import type { Player } from '../data/types'
import type { DataSource } from '../data/useTableData'
import { Avatar, Pill } from './ui'

interface TopbarProps {
  title: string
  live: boolean
  source: DataSource
  players: Player[]
}

export function Topbar({ title, live, source, players }: TopbarProps) {
  return (
    <header
      className={css({
        h: '80px',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        pl: '36px',
        pr: '32px',
        borderBottom: '1px solid',
        borderColor: 'line',
      })}
    >
      <h1 className={css({ textStyle: 'pageTitle', color: 'text' })}>{title}</h1>
      {live ? <Pill tone="live">Live</Pill> : <Pill tone="neutral">Powtórka</Pill>}

      <div className={css({ ml: 'auto', display: 'flex', alignItems: 'center', gap: '12px' })}>
        <span
          title={source === 'backend' ? 'Pozycje bil z kamery Raspberry Pi' : 'Backend niedostępny – dane przykładowe'}
          className={css({ textStyle: 'eyebrow', color: 'textSubtle', mr: '12px' })}
        >
          {source === 'backend' ? 'Dane: backend' : 'Dane: mock'}
        </span>
        <span className={css({ textStyle: 'body', color: 'textSubtle' })}>
          {players.map((p) => p.name.split(' ')[0]).join(' x ')}
        </span>
        <div className={css({ display: 'flex' })}>
          {players.map((p, i) => (
            <Avatar
              key={p.id}
              size={32}
              tone={i === 0 ? 'accent' : 'live'}
              className={css({ border: '2px solid', borderColor: 'canvas', '&:not(:first-child)': { ml: '-4px' } })}
            />
          ))}
        </div>
      </div>
    </header>
  )
}
