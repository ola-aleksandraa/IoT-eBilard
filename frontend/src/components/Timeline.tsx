import { css, cx } from '../../styled-system/css'
import { Card, Eyebrow } from './ui'

interface TimelineProps {
  count: number
  index: number
  playing: boolean
  onSeek: (index: number) => void
  onTogglePlay: () => void
}

const roundButton = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: '999px',
  cursor: 'pointer',
  flexShrink: 0,
  transition: 'transform 120ms, background 120ms, opacity 120ms',
  _focusVisible: { outline: '2px solid', outlineColor: 'accent', outlineOffset: '3px' },
  _disabled: { opacity: 0.4, cursor: 'default' },
})

const stepButton = cx(
  roundButton,
  css({
    w: '36px',
    h: '36px',
    bg: 'chip',
    border: '1px solid',
    borderColor: 'lineStrong',
    color: 'textMuted',
    _hover: { _enabled: { color: 'text', bg: 'lineStrong' } },
  }),
)

export function Timeline({ count, index, playing, onSeek, onTogglePlay }: TimelineProps) {
  const last = count - 1
  const pct = (i: number) => `${(i / last) * 100}%`

  return (
    <Card label="Historia stołu" className={css({ px: '24px', pt: '20px', pb: '37px', minW: 0 })}>
      <Eyebrow>Historia stołu</Eyebrow>
      <div className={css({ display: 'flex', alignItems: 'flex-start', mt: '14px' })}>
        <button
          type="button"
          onClick={onTogglePlay}
          aria-label={playing ? 'Pauza' : 'Odtwórz historię'}
          className={cx(
            roundButton,
            css({ w: '52px', h: '52px', bg: 'accent', color: 'canvas', boxShadow: 'glow', _hover: { transform: 'scale(1.04)' } }),
          )}
        >
          {playing ? (
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
              <rect x="3" y="1" width="3.5" height="14" rx="1" fill="currentColor" />
              <rect x="9.5" y="1" width="3.5" height="14" rx="1" fill="currentColor" />
            </svg>
          ) : (
            <svg width="16" height="18" viewBox="0 0 16 18" aria-hidden className={css({ ml: '3px' })}>
              <path d="M2 1L15 9L2 17Z" fill="currentColor" />
            </svg>
          )}
        </button>
        <button
          type="button"
          className={cx(stepButton, css({ ml: '14px', mt: '8px' }))}
          aria-label="Poprzedni stan"
          disabled={index === 0}
          onClick={() => onSeek(index - 1)}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M10 1L2 6L10 11Z M0 1H2V11H0Z" fill="currentColor" />
          </svg>
        </button>
        <button
          type="button"
          className={cx(stepButton, css({ ml: '8px', mt: '8px' }))}
          aria-label="Następny stan"
          disabled={index === last}
          onClick={() => onSeek(index + 1)}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M1 1L9 6L1 11Z M10 1H12V11H10Z" fill="currentColor" />
          </svg>
        </button>

        <div className={css({ flex: 1, minW: 0, ml: '22px', mr: '2px', pt: '19px' })}>
          <div className={css({ position: 'relative', h: '14px', mx: '7px' })}>
            <div className={css({ position: 'absolute', top: '5px', left: 0, right: 0, h: '4px', borderRadius: '999px', bg: 'lineStrong' })} />
            <div
              className={css({ position: 'absolute', top: '5px', left: 0, h: '4px', borderRadius: '999px', bg: 'accent', transition: 'width 200ms' })}
              style={{ width: pct(index) }}
            />
            {Array.from({ length: count }, (_, i) => {
              const current = i === index
              return (
                <button
                  key={i}
                  type="button"
                  aria-label={i === 0 ? 'Rozbicie' : i === last ? 'Teraz' : `Stan ${i}`}
                  aria-current={current ? 'step' : undefined}
                  onClick={() => onSeek(i)}
                  className={css({
                    position: 'absolute',
                    top: '50%',
                    w: '18px',
                    h: '18px',
                    transform: 'translate(-50%, -50%)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '999px',
                    _focusVisible: { outline: '2px solid', outlineColor: 'accent' },
                    '&:hover > span': { transform: 'scale(1.3)' },
                  })}
                  style={{ left: pct(i) }}
                >
                  <span
                    className={cx(
                      css({ display: 'block', borderRadius: '999px', transition: 'transform 120ms' }),
                      current
                        ? css({ w: '14px', h: '14px', bg: 'accent', border: '3px solid', borderColor: 'surface', boxShadow: 'glow' })
                        : css({ w: '7px', h: '7px' }),
                      !current && (i < index ? css({ bg: 'accent' }) : css({ bg: 'lineStrong' })),
                    )}
                  />
                </button>
              )
            })}
          </div>
          <div className={css({ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mt: '5px', textStyle: 'body' })}>
            <span className={css({ color: 'textSubtle', ml: '-6px', mt: '6px' })}>Rozbicie</span>
            <span className={cx(css({ mr: '-14px' }), index === last ? css({ color: 'accent' }) : css({ color: 'textSubtle' }))}>
              teraz
            </span>
          </div>
        </div>
      </div>
    </Card>
  )
}
