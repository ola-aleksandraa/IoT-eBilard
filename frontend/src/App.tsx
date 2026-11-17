import { useEffect, useState } from 'react'
import { css } from '../styled-system/css'
import { SvgDefs } from './components/Ball'
import { HintCard } from './components/HintCard'
import { HitPointFront, HitPointSide } from './components/HitPoint'
import { PlayersCard } from './components/PlayersCard'
import { PoolTable } from './components/PoolTable'
import { RulesPage } from './components/RulesPage'
import { Sidebar, type NavId } from './components/Sidebar'
import { Timeline } from './components/Timeline'
import { Topbar } from './components/Topbar'
import { Card, Pill, StatCard } from './components/ui'
import { averageTurn, session, stats } from './data/mock'
import type { HitPoint } from './data/types'
import { useTableData, type TableData } from './data/useTableData'

const PLAYBACK_MS = 700

function formatClock(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function useTurnClock(startSecondsAgo: number) {
  const [seconds, setSeconds] = useState(startSecondsAgo)
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])
  return seconds
}

export default function App() {
  const [page, setPage] = useState<NavId>('table')
  const data = useTableData()

  return (
    <div className={css({ display: 'flex', minH: '100vh', minW: '1280px', bg: 'canvas' })}>
      <SvgDefs />
      <Sidebar active={page} onNavigate={setPage} user={session.me} />
      <div className={css({ flex: 1, minW: 0, display: 'flex', flexDirection: 'column' })}>
        {page === 'table' ? (
          <TablePage key={data.source} data={data} />
        ) : (
          <>
            <Topbar title={PAGE_TITLES[page]} live source={data.source} players={session.players} />
            {page === 'rules' ? (
              <RulesPage />
            ) : (
              <main className={css({ p: '24px 32px 24px 36px' })}>
                <Card className={css({ p: '24px', textStyle: 'body', color: 'textMuted' })}>Ten widok nie ma jeszcze projektu.</Card>
              </main>
            )}
          </>
        )}
      </div>
    </div>
  )
}

const PAGE_TITLES: Record<NavId, string> = {
  table: 'Podgląd stołu',
  rules: 'Zasady',
  settings: 'Ustawienia',
  view: 'Widok',
}

function TablePage({ data }: { data: TableData }) {
  const { history } = data
  const last = history.length - 1
  const [index, setIndex] = useState(last)
  const [playing, setPlaying] = useState(false)
  const [hintActive, setHintActive] = useState(false)
  // A hint is paid for once per layout; afterwards it can be shown and hidden for free.
  const [hintUnlocked, setHintUnlocked] = useState(false)
  const [hintsLeft, setHintsLeft] = useState(session.hintsLeft)
  const [hit, setHit] = useState<HitPoint>({ x: 0.38, y: 0.5 })
  const turnSeconds = useTurnClock(session.turnStartedSecondsAgo)

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      setIndex((i) => {
        if (i >= last) {
          setPlaying(false)
          return i
        }
        return i + 1
      })
    }, PLAYBACK_MS)
    return () => clearInterval(id)
  }, [playing, last])

  const isLive = index === last
  const snapshot = history[index]
  const shot = isLive ? (hintActive ? data.hint : data.predicted) : null
  const active = session.players.find((p) => p.id === session.activePlayerId)!

  const togglePlay = () => {
    if (!playing && index === last) setIndex(0)
    setPlaying((p) => !p)
  }
  const seek = (i: number) => {
    setPlaying(false)
    setIndex(Math.max(0, Math.min(last, i)))
  }
  const toggleHint = () => {
    if (!hintActive) {
      if (!hintUnlocked) {
        setHintsLeft((n) => n - 1)
        setHintUnlocked(true)
      }
      seek(last)
    }
    setHintActive((a) => !a)
  }

  return (
    <>
      <Topbar title="Podgląd stołu" live={isLive} source={data.source} players={session.players} />
      <main
        className={css({
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 380px',
          columnGap: '19px',
          alignItems: 'start',
          pt: '24px',
          pb: '32px',
          pl: '36px',
          pr: '32px',
        })}
      >
        <div className={css({ display: 'flex', flexDirection: 'column', minW: 0 })}>
          <div className={css({ display: 'flex', alignItems: 'center', gap: '13px', h: '26px', mb: '11px' })}>
            <h2 className={css({ textStyle: 'section', color: 'text', mr: 'auto' })}>Aktualne ustawienie</h2>
            <Pill tone="accent">Kolej: {active.name.split(' ')[0]}</Pill>
            <Pill tone="neutral">Runda {session.round}</Pill>
          </div>

          <Card
            label="Stół"
            className={css({
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              py: '42px',
              px: '50px',
              boxShadow: 'card',
            })}
          >
            <PoolTable balls={snapshot.balls} shot={shot} />
          </Card>

          <div className={css({ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 250px', gap: '13px', mt: '23px' })}>
            <div className={css({ display: 'flex', flexDirection: 'column', gap: '14px', minW: 0 })}>
              <Timeline count={history.length} index={index} playing={playing} onSeek={seek} onTogglePlay={togglePlay} />
              <div className={css({ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '16px' })}>
                {stats.map((s) => (
                  <StatCard key={s.label} {...s} />
                ))}
                <StatCard label="Czas tury" value={formatClock(turnSeconds)} hint={`średnia: ${averageTurn}`} />
              </div>
            </div>
            <PlayersCard players={session.players} activeId={session.activePlayerId} />
          </div>
        </div>

        <aside className={css({ display: 'flex', flexDirection: 'column', gap: '12px', pt: '36px' })} aria-label="Narzędzia uderzenia">
          <HintCard
            hintsLeft={hintsLeft}
            hintsTotal={session.hintsTotal}
            active={hintActive}
            unlocked={hintUnlocked}
            available={data.hint != null}
            onToggle={toggleHint}
          />
          {hintActive && (
            <>
              <HitPointFront value={hit} onChange={setHit} />
              <HitPointSide value={hit} />
            </>
          )}
        </aside>
      </main>
    </>
  )
}
