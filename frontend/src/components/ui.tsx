import type { CSSProperties, ReactNode } from 'react'
import { css, cx } from '../../styled-system/css'

const cardClass = css({
  bg: 'surface',
  border: '1px solid', borderColor: 'line',
  borderRadius: '14px',
  position: 'relative',
  overflow: 'hidden',
})

export function Card({
  children,
  className,
  label,
  style,
}: {
  children: ReactNode
  className?: string
  label?: string
  style?: CSSProperties
}) {
  return (
    <section className={cx(cardClass, className)} aria-label={label} style={style}>
      {children}
    </section>
  )
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={cx(css({ textStyle: 'eyebrow', color: 'textSubtle' }), className)}>{children}</h3>
}

const pillTones = {
  accent: css({ bg: 'accentSoft', color: 'accent' }),
  live: css({ bg: 'liveSoft', color: 'live' }),
  danger: css({ bg: 'dangerSoft', color: 'danger' }),
  neutral: css({ bg: 'chip', color: 'textMuted' }),
}

export function Pill({ tone, children }: { tone: keyof typeof pillTones; children: ReactNode }) {
  return (
    <span
      className={cx(
        css({
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          px: '10px',
          py: '5px',
          borderRadius: '999px',
          textStyle: 'eyebrow',
          whiteSpace: 'nowrap',
        }),
        pillTones[tone],
      )}
    >
      {children}
    </span>
  )
}

const avatarTones = {
  accent: css({ bg: 'accent', color: 'canvas' }),
  live: css({ bg: 'live', color: 'canvas' }),
  neutral: css({ bg: 'lineStrong', color: 'text' }),
}

export function Avatar({
  initials,
  size,
  tone = 'accent',
  className,
}: {
  initials?: string
  size: number
  tone?: keyof typeof avatarTones
  className?: string
}) {
  return (
    <span
      className={cx(
        css({
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          borderRadius: '999px',
          textStyle: 'control',
        }),
        avatarTones[tone],
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden={!initials}
    >
      {initials}
    </span>
  )
}

export function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint: string }) {
  return (
    <div
      className={css({
        bg: 'surface',
        border: '1px solid', borderColor: 'line',
        borderRadius: '10px',
        p: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        minW: 0,
      })}
    >
      <Eyebrow>{label}</Eyebrow>
      <p className={css({ textStyle: 'stat', color: 'text', fontVariantNumeric: 'tabular-nums' })}>{value}</p>
      <p className={css({ textStyle: 'body', color: 'textSubtle' })}>{hint}</p>
    </div>
  )
}
