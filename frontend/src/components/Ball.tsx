import { ballColor, IVORY } from '../data/balls'
import type { BallLook } from '../data/types'

/**
 * Shared SVG definitions (filters, clip paths). Mounted once at the app root;
 * every other SVG references them by id. All ball effects are expressed in a
 * 30×30 local space so they scale with the ball.
 */
export function SvgDefs() {
  return (
    <svg width="0" height="0" aria-hidden style={{ position: 'absolute' }}>
      <defs>
        <clipPath id="eb-ball-clip">
          <circle cx="15" cy="15" r="15" />
        </clipPath>
        {/* Figma: drop shadow (0.75, 2.25) blur 4.5 @55%, inner shadow (-1.5, -2.25) blur 4.5 @35% */}
        <filter id="eb-ball-fx" x="-40%" y="-40%" width="180%" height="180%" colorInterpolationFilters="sRGB">
          <feGaussianBlur in="SourceAlpha" stdDeviation="2.25" />
          <feOffset dx="0.75" dy="2.25" result="dropBlur" />
          <feFlood floodColor="#000" floodOpacity="0.55" />
          <feComposite in2="dropBlur" operator="in" result="drop" />
          <feOffset in="SourceAlpha" dx="-1.5" dy="-2.25" />
          <feGaussianBlur stdDeviation="2.25" result="innerBlur" />
          <feComposite in="SourceAlpha" in2="innerBlur" operator="arithmetic" k2="1" k3="-1" result="innerMask" />
          <feFlood floodColor="#000" floodOpacity="0.35" />
          <feComposite in2="innerMask" operator="in" result="inner" />
          <feMerge>
            <feMergeNode in="drop" />
            <feMergeNode in="SourceGraphic" />
            <feMergeNode in="inner" />
          </feMerge>
        </filter>
        <InnerShadow id="eb-felt-fx" blur={34} opacity={0.55} />
        <InnerShadow id="eb-preview-fx" blur={16} opacity={0.5} />
        <InnerShadow id="eb-pocket-fx" blur={6} dy={2} opacity={0.9} />
      </defs>
    </svg>
  )
}

function InnerShadow({ id, blur, dy = 0, opacity }: { id: string; blur: number; dy?: number; opacity: number }) {
  return (
    <filter id={id} x="-10%" y="-10%" width="120%" height="120%" colorInterpolationFilters="sRGB">
      <feOffset in="SourceAlpha" dy={dy} />
      <feGaussianBlur stdDeviation={blur / 2} result="blur" />
      <feComposite in="SourceAlpha" in2="blur" operator="arithmetic" k2="1" k3="-1" result="mask" />
      <feFlood floodColor="#000" floodOpacity={opacity} />
      <feComposite in2="mask" operator="in" result="shadow" />
      <feMerge>
        <feMergeNode in="SourceGraphic" />
        <feMergeNode in="shadow" />
      </feMerge>
    </filter>
  )
}

interface BallProps {
  ball: BallLook
  cx: number
  cy: number
  r: number
  /** Plain ivory sphere without highlight/shade (used for the large cue-ball views). */
  plain?: boolean
  opacity?: number
}

/** A billiard ball drawn inside an existing <svg>, centred at (cx, cy). */
export function Ball({ ball, cx, cy, r, plain, opacity }: BallProps) {
  const color = ballColor(ball)
  const striped = ball.kind === 'striped'
  const body = striped || ball.kind === 'cue' ? IVORY : color
  const label = ball.number ?? (ball.kind === 'eight' ? 8 : undefined)
  return (
    <svg x={cx - r} y={cy - r} width={r * 2} height={r * 2} viewBox="0 0 30 30" overflow="visible" opacity={opacity}>
      <circle cx="15" cy="15" r="15" fill={body} filter="url(#eb-ball-fx)" />
      {!plain && (
        <g clipPath="url(#eb-ball-clip)">
          {striped && <rect x="0" y="6.5" width="30" height="17" fill={color} />}
          <ellipse cx="11.5" cy="8.5" rx="6.5" ry="4.5" fill="#fff" fillOpacity="0.32" />
          <ellipse cx="16" cy="23" rx="8" ry="6" fill="#000" fillOpacity="0.22" />
          {label != null && (
            <>
              <circle cx="15" cy="15" r="8" fill="#fbf8f0" />
              <text
                x="15"
                y="15.5"
                textAnchor="middle"
                dominantBaseline="middle"
                fontFamily="Inter, sans-serif"
                fontWeight="700"
                fontSize={label >= 10 ? 8.5 : 9}
                fill="#16181c"
              >
                {label}
              </text>
            </>
          )}
        </g>
      )}
    </svg>
  )
}

/** Stand-alone ball for use in HTML layouts (logo, player badges). */
export function BallIcon({ ball, size, className }: { ball: BallLook; size: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ overflow: 'visible' }}
      role="img"
      aria-label={ball.number != null ? `Bila ${ball.number}` : 'Bila'}
    >
      <Ball ball={ball} cx={size / 2} cy={size / 2} r={size / 2} />
    </svg>
  )
}
