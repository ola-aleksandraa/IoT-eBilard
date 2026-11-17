import { css, cx } from '../../styled-system/css'
import { Avatar } from './ui'
import { BallIcon } from './Ball'

const NAV = [
  { id: 'table', label: 'Stan stołu' },
  { id: 'rules', label: 'Zasady' },
  { id: 'settings', label: 'Ustawienia' },
  { id: 'view', label: 'Widok' },
] as const

export type NavId = (typeof NAV)[number]['id']

const itemClass = css({
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  w: 'full',
  h: '44px',
  px: '14px',
  borderRadius: '10px',
  textStyle: 'control',
  color: 'textMuted',
  textAlign: 'left',
  cursor: 'pointer',
  transition: 'background 120ms, color 120ms',
  _hover: { bg: 'chip', color: 'text' },
  _focusVisible: { outline: '2px solid', outlineColor: 'accent', outlineOffset: '2px' },
})

const activeClass = css({
  bg: 'accentSoft',
  color: 'accent',
  _hover: { bg: 'accentSoft', color: 'accent' },
})

interface SidebarProps {
  active: NavId
  onNavigate: (id: NavId) => void
  user: { name: string; initials: string; level: string }
}

export function Sidebar({ active, onNavigate, user }: SidebarProps) {
  return (
    <aside
      className={css({
        position: 'sticky',
        top: 0,
        h: '100vh',
        w: '264px',
        flexShrink: 0,
        bg: 'surface',
        borderRight: '1px solid',
        borderColor: 'line',
        display: 'flex',
        flexDirection: 'column',
        px: '20px',
        pb: '20px',
      })}
    >
      <div className={css({ display: 'flex', alignItems: 'flex-start', gap: '10px', pt: '32px', pl: '8px' })}>
        <BallIcon ball={{ kind: 'eight', number: 8 }} size={34} />
        <span className={css({ textStyle: 'eyebrow', color: 'text', mt: '4px' })}>eBilard</span>
      </div>

      <nav aria-label="Nawigacja" className={css({ mt: '42px' })}>
        <p className={css({ textStyle: 'eyebrow', color: 'textSubtle', pl: '8px', mb: '14px' })}>Nawigacja</p>
        <ul className={css({ display: 'flex', flexDirection: 'column', gap: '0' })}>
          {NAV.map((item) => {
            const isActive = item.id === active
            return (
              <li key={item.id} className={css({ '&:first-child': { mb: '14px' } })}>
                <button
                  type="button"
                  className={cx(itemClass, isActive && activeClass)}
                  aria-current={isActive ? 'page' : undefined}
                  onClick={() => onNavigate(item.id)}
                >
                  <span
                    className={cx(
                      css({ w: '8px', h: '8px', borderRadius: '999px', flexShrink: 0 }),
                      isActive ? css({ bg: 'accent' }) : css({ bg: 'textSubtle' }),
                    )}
                  />
                  {item.label}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div
        className={css({
          mt: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          p: '10px',
          bg: 'sunken',
          border: '1px solid',
          borderColor: 'line',
          borderRadius: '10px',
        })}
      >
        <Avatar initials={user.initials} size={36} />
        <div className={css({ minW: 0 })}>
          <p className={css({ textStyle: 'name', color: 'text' })}>{user.name}</p>
          <p className={css({ textStyle: 'body', color: 'textSubtle', truncate: true })}>{user.level}</p>
        </div>
      </div>
    </aside>
  )
}
