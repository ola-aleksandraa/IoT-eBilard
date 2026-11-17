import { useState, type CSSProperties, type ReactNode } from 'react'
import { css, cx } from '../../styled-system/css'
import { history, session } from '../data/mock'
import type { BallLook } from '../data/types'
import { BallIcon } from './Ball'
import { PoolTable } from './PoolTable'
import { Card, Eyebrow, Pill } from './ui'

// Rules of eight-ball (simplified WPA rules) plus the eBilard-specific mechanics.

const RACK = history[0].balls

// Entrance choreography: every block rises in after the previous one, in reading order,
// so the page walks through the rules step by step. Times in ms from mount.
const T = {
  header: 0,
  table: 120,
  goal: 260,
  group: (i: number) => 420 + i * 90,
  step: (i: number) => 720 + i * 260,
  fouls: 1800,
  losses: 2050,
  item: (start: number, i: number) => start + 140 + i * 80,
  app: 2400,
  appItem: (i: number) => 2520 + i * 140,
}

const reveal = css({
  animation: 'rise 560ms cubic-bezier(0.2, 0.7, 0.2, 1) both',
  _motionReduce: { animation: 'none' },
})

const at = (ms: number): CSSProperties => ({ animationDelay: `${ms}ms` })

const SOLIDS: BallLook[] = [1, 2, 3, 4, 5, 6, 7].map((number) => ({ kind: 'solid', number }))
const STRIPES: BallLook[] = [9, 10, 11, 12, 13, 14, 15].map((number) => ({ kind: 'striped', number }))
const EIGHT: BallLook = { kind: 'eight', number: 8 }

const STEPS: { title: string; body: ReactNode }[] = [
  {
    title: 'Rozbicie',
    body: (
      <>
        Rozbijający uderza białą zza linii bazy. Rozbicie jest prawidłowe, gdy wpadnie co najmniej jedna bila albo
        cztery bile dotkną band. Wbicie 8 przy rozbiciu nie przegrywa – bile ustawia się ponownie.
      </>
    ),
  },
  {
    title: 'Stół otwarty',
    body: (
      <>
        Po rozbiciu grupy nie są przypisane. Pierwsza prawidłowo wbita bila wyznacza twoją grupę – pełne albo połówki.
        Przeciwnik dostaje drugą.
      </>
    ),
  },
  {
    title: 'Twoja tura',
    body: (
      <>
        Grasz, dopóki wbijasz bile ze swojej grupy. Biała musi najpierw trafić twoją bilę, a potem coś musi wpaść lub
        dotknąć bandy. Pudło oddaje stół bez kary.
      </>
    ),
  },
  {
    title: 'Bila 8',
    body: (
      <>
        Gdy twoja grupa jest zbita, celujesz w 8. Zapowiedz łuzę – wbicie 8 do zapowiedzianej łuzy wygrywa partię.
      </>
    ),
  },
]

const FOULS = [
  'Biała wpada do łuzy lub wypada ze stołu',
  'Biała najpierw trafia bilę przeciwnika albo 8',
  'Po kontakcie nic nie wpada i żadna bila nie dotyka bandy',
  'Bila zagrywana wyskakuje poza stół',
  'Dotknięcie bili ręką, ubraniem lub kijem poza uderzeniem',
]

const LOSSES = [
  'Wbicie 8, zanim zbijesz swoją grupę',
  'Wbicie 8 do innej łuzy niż zapowiedziana',
  'Faul przy wbiciu 8 – np. biała wpada razem z nią',
  'Wybicie 8 poza stół',
]

const APP_RULES: { title: string; body: string }[] = [
  {
    title: 'Podpowiedzi',
    body: `Masz ${session.hintsTotal} na partię. „Pomóż mi” zużywa jedną i rysuje sugerowane uderzenie. Dla tego samego układu możesz ją potem chować i pokazywać za darmo.`,
  },
  {
    title: 'Punkt uderzenia',
    body: 'Przy podpowiedzi wybierasz miejsce styku kija z białą: góra – bila jedzie dalej, dół – cofa się, boki – podkręcenie w lewo lub prawo.',
  },
  {
    title: 'Powtórka',
    body: 'Oś czasu pod stołem cofa do wcześniejszych ustawień. Na ostatniej klatce podgląd wraca do trybu Live.',
  },
  {
    title: 'Czas tury',
    body: 'Licznik startuje z początkiem twojej tury. Obok widzisz swoją średnią z partii.',
  },
]

export function RulesPage() {
  // Bumping the key remounts the page, which restarts every animation.
  const [run, setRun] = useState(0)
  return (
    <main
      key={run}
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
        <div
          className={cx(reveal, css({ display: 'flex', alignItems: 'center', gap: '13px', h: '26px', mb: '11px' }))}
          style={at(T.header)}
        >
          <h2 className={css({ textStyle: 'section', color: 'text', mr: 'auto' })}>Ósemka w skrócie</h2>
          <Pill tone="accent">2 graczy</Pill>
          <Pill tone="neutral">15 bil + biała</Pill>
          <button type="button" onClick={() => setRun((n) => n + 1)} className={replayClass}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
              <path d="M2 6a4 4 0 1 0 1.2-2.85M2 1.5v2.5h2.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Pokaż od nowa
          </button>
        </div>

        <Card
          label="Ustawienie początkowe"
          style={at(T.table)}
          className={cx(reveal, css({ display: 'flex', flexDirection: 'column', alignItems: 'center', py: '42px', px: '50px', boxShadow: 'card' }))}
        >
          <PoolTable balls={RACK} label="Ustawienie bil przed rozbiciem" />
          <p className={css({ textStyle: 'body', color: 'textMuted', mt: '28px', textAlign: 'center', maxW: '560px' })}>
            Bile w trójkącie, 8 w środku trzeciego rzędu, w tylnych rogach jedna pełna i jedna połówka. Biała stoi za
            linią bazy po lewej.
          </p>
        </Card>

        <ol className={css({ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '16px', mt: '23px' })}>
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              style={at(T.step(i))}
              className={cx(reveal, css({
                bg: 'surface',
                border: '1px solid',
                borderColor: 'line',
                borderRadius: '10px',
                p: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                minW: 0,
              }))}
            >
              <StepNumber n={i + 1} />
              <h3 className={css({ textStyle: 'cardTitle', color: 'text', mt: '4px' })}>{step.title}</h3>
              <p className={css({ textStyle: 'body', color: 'textMuted' })}>{step.body}</p>
            </li>
          ))}
        </ol>

        <div className={css({ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '16px', mt: '16px' })}>
          <RuleList
            label="Faule"
            title="Faul – bila z ręki dla rywala"
            note="Przeciwnik stawia białą w dowolnym miejscu stołu i zaczyna swoją turę."
            items={FOULS}
            tone="warn"
            delay={T.fouls}
          />
          <RuleList
            label="Przegrana"
            title="Przegrywasz od razu, gdy…"
            note="Partia kończy się natychmiast, niezależnie od liczby bil na stole."
            items={LOSSES}
            tone="danger"
            delay={T.losses}
          />
        </div>
      </div>

      <aside className={css({ display: 'flex', flexDirection: 'column', gap: '12px', pt: '37px' })} aria-label="Ściąga">
        <Card label="Cel gry" className={cx(reveal, css({ p: '20px' }))} style={at(T.goal)}>
          <Eyebrow>Cel gry</Eyebrow>
          <h4 className={css({ textStyle: 'cardTitle', color: 'text', mt: '12px' })}>Zbij swoją grupę, potem 8</h4>
          <p className={css({ textStyle: 'body', color: 'textMuted', mt: '4px' })}>
            Każdy gracz ma siedem bil. Wygrywa ten, kto pierwszy prawidłowo wbije 8.
          </p>
          <div className={css({ display: 'flex', flexDirection: 'column', gap: '8px', mt: '16px' })}>
            <BallGroup name="Pełne" range="1–7" balls={SOLIDS} delay={T.group(0)} />
            <BallGroup name="Połówki" range="9–15" balls={STRIPES} delay={T.group(1)} />
            <BallGroup name="Czarna" range="na koniec" balls={[EIGHT]} delay={T.group(2)} highlight />
          </div>
        </Card>

        <Card label="Zasady eBilard" className={cx(reveal, css({ px: '16px', pt: '20px', pb: '16px' }))} style={at(T.app)}>
          <Eyebrow className={css({ px: '4px' })}>W eBilard</Eyebrow>
          <ul className={css({ display: 'flex', flexDirection: 'column', gap: '6px', mt: '14px' })}>
            {APP_RULES.map((rule, i) => (
              <li
                key={rule.title}
                style={at(T.appItem(i))}
                className={cx(reveal, css({ p: '12px', borderRadius: '10px', bg: 'sunken', border: '1px solid', borderColor: 'line' }))}
              >
                <p className={css({ textStyle: 'name', color: 'text' })}>{rule.title}</p>
                <p className={css({ textStyle: 'body', color: 'textMuted', mt: '2px' })}>{rule.body}</p>
              </li>
            ))}
          </ul>
        </Card>
      </aside>
    </main>
  )
}

const replayClass = css({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  h: '26px',
  px: '10px',
  borderRadius: '999px',
  border: '1px solid',
  borderColor: 'line',
  color: 'textMuted',
  textStyle: 'eyebrow',
  cursor: 'pointer',
  transition: 'background 120ms, color 120ms, border-color 120ms',
  _hover: { bg: 'chip', color: 'text', borderColor: 'lineStrong' },
  _focusVisible: { outline: '2px solid', outlineColor: 'accent', outlineOffset: '2px' },
})

function StepNumber({ n }: { n: number }) {
  return (
    <span
      aria-hidden
      className={css({
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        w: '28px',
        h: '28px',
        borderRadius: '999px',
        bg: 'accentSoft',
        color: 'accent',
        textStyle: 'control',
        fontVariantNumeric: 'tabular-nums',
      })}
    >
      {n}
    </span>
  )
}

function BallGroup({
  name,
  range,
  balls,
  delay,
  highlight,
}: {
  name: string
  range: string
  balls: BallLook[]
  delay: number
  highlight?: boolean
}) {
  return (
    <div
      style={at(delay)}
      className={cx(
        reveal,
        css({ display: 'flex', alignItems: 'center', gap: '12px', p: '10px 12px', borderRadius: '10px', border: '1px solid' }),
        highlight ? css({ bg: 'accentSoft', borderColor: 'accent' }) : css({ bg: 'sunken', borderColor: 'line' }),
      )}
    >
      <div className={css({ w: '64px', flexShrink: 0 })}>
        <p className={css({ textStyle: 'name', color: 'text' })}>{name}</p>
        <p className={css({ textStyle: 'body', color: highlight ? 'accent' : 'textSubtle' })}>{range}</p>
      </div>
      <div className={css({ display: 'flex', gap: '4px', flexWrap: 'wrap' })}>
        {balls.map((b) => (
          <BallIcon key={b.number} ball={b} size={26} />
        ))}
      </div>
    </div>
  )
}

const listTones = {
  warn: { dot: css({ bg: 'live' }), pill: 'live' as const, pillText: 'Bila z ręki' },
  danger: { dot: css({ bg: 'danger' }), pill: 'danger' as const, pillText: 'Koniec partii' },
}

function RuleList({
  label,
  title,
  note,
  items,
  tone,
  delay,
}: {
  label: string
  title: string
  note: string
  items: string[]
  tone: keyof typeof listTones
  delay: number
}) {
  const t = listTones[tone]
  return (
    <Card label={label} className={cx(reveal, css({ p: '20px', display: 'flex', flexDirection: 'column' }))} style={at(delay)}>
      <div className={css({ display: 'flex', alignItems: 'center', gap: '8px' })}>
        <Eyebrow className={css({ mr: 'auto' })}>{label}</Eyebrow>
        <Pill tone={t.pill}>{t.pillText}</Pill>
      </div>
      <h4 className={css({ textStyle: 'cardTitle', color: 'text', mt: '12px' })}>{title}</h4>
      <ul className={css({ display: 'flex', flexDirection: 'column', gap: '10px', mt: '14px' })}>
        {items.map((item, i) => (
          <li key={item} style={at(T.item(delay, i))} className={cx(reveal, css({ display: 'flex', alignItems: 'baseline', gap: '10px', textStyle: 'body', color: 'text' }))}>
            <span className={cx(css({ w: '8px', h: '8px', borderRadius: '999px', flexShrink: 0, transform: 'translateY(-1px)' }), t.dot)} />
            {item}
          </li>
        ))}
      </ul>
      <p className={css({ textStyle: 'body', color: 'textSubtle', mt: 'auto', pt: '16px' })}>{note}</p>
    </Card>
  )
}
