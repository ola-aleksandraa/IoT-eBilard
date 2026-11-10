import { css } from '../../styled-system/css'
import { Ball } from './Ball'
import { Card, Eyebrow } from './ui'

interface HintCardProps {
  hintsLeft: number
  hintsTotal: number
  active: boolean
  /** Already paid for – showing it again is free. */
  unlocked: boolean
  /** False when there is no suggestion for the current layout. */
  available: boolean
  onToggle: () => void
}

export function HintCard({ hintsLeft, hintsTotal, active, unlocked, available, onToggle }: HintCardProps) {
  const disabled = !active && !unlocked && (hintsLeft === 0 || !available)
  return (
    <Card label="Podpowiedź" className={css({ p: '20px', flexShrink: 0 })}>
      <Eyebrow>Nie wiesz co zrobić?</Eyebrow>
      <HintPreview />
      <h4 className={css({ textStyle: 'cardTitle', color: 'text', mt: '12px' })}>Wykorzystaj podpowiedź</h4>
      <p className={css({ textStyle: 'body', color: 'textMuted', mt: '4px' })}>
        {!available
          ? 'Brak podpowiedzi dla tego układu'
          : unlocked
            ? `Już opłacona · zostały ci ${hintsLeft}/${hintsTotal} wskazówki`
            : hintsLeft > 0
              ? `Zostały ci ${hintsLeft}/${hintsTotal} wskazówki`
              : 'Wykorzystano wszystkie wskazówki'}
      </p>
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        aria-pressed={active}
        className={css({
          mt: '5px',
          w: 'full',
          h: '42px',
          px: '20px',
          borderRadius: '10px',
          bg: 'accent',
          color: 'canvas',
          textStyle: 'control',
          boxShadow: 'glow',
          cursor: 'pointer',
          transition: 'filter 120ms, opacity 120ms',
          _hover: { _enabled: { filter: 'brightness(1.08)' } },
          _focusVisible: { outline: '2px solid', outlineColor: 'accent', outlineOffset: '3px' },
          _disabled: { opacity: 0.4, cursor: 'not-allowed', boxShadow: 'none' },
        })}
      >
        {active ? 'Ukryj podpowiedź' : unlocked ? 'Pokaż podpowiedź' : 'Pomóż mi'}
      </button>
    </Card>
  )
}

/** Small schematic of the suggested shot (target pocket → object ball ← cue ball). */
function HintPreview() {
  return (
    <svg
      viewBox="0 0 340 96"
      className={css({ display: 'block', w: 'full', h: 'auto', mt: '10px', borderRadius: '8px', overflow: 'hidden' })}
      aria-hidden
    >
      <rect width="340" height="96" fill="#0f5c46" filter="url(#eb-preview-fx)" />
      <circle cx="4" cy="4" r="11" fill="#06090c" stroke="#b8ff3c" strokeWidth="2" />
      <line x1="46" y1="20" x2="180" y2="44" stroke="#b8ff3c" strokeWidth="2" strokeDasharray="6 5" strokeLinecap="round" />
      <line x1="180" y1="44" x2="290" y2="66" stroke="#4dd8ff" strokeWidth="2" strokeDasharray="6 5" strokeLinecap="round" />
      <Ball ball={{ kind: 'solid', number: 5 }} cx={180} cy={44} r={11} />
      <Ball ball={{ kind: 'cue' }} cx={290} cy={66} r={11} />
    </svg>
  )
}
