import { defineConfig } from '@pandacss/dev'

// Design tokens taken from the Figma file "eBilard" (desktop frame "01 · Stan stolu").
export default defineConfig({
  presets: ['@pandacss/preset-base', '@pandacss/preset-panda'],
  preflight: true,
  include: ['./src/**/*.{js,jsx,ts,tsx}'],
  exclude: [],
  jsxFramework: 'react',
  globalCss: {
    'html, body': {
      bg: 'canvas',
      color: 'text',
      fontFamily: 'sans',
      WebkitFontSmoothing: 'antialiased',
    },
  },
  theme: {
    extend: {
      tokens: {
        fonts: {
          sans: { value: "'Inter', ui-sans-serif, system-ui, sans-serif" },
          mono: { value: "'JetBrains Mono', ui-monospace, monospace" },
        },
        colors: {
          // surfaces
          canvas: { value: '#0b0e13' },
          surface: { value: '#141a22' },
          sunken: { value: '#0f141b' },
          chip: { value: '#1c242f' },
          line: { value: '#263040' },
          lineStrong: { value: '#3a4759' },
          // text
          text: { value: '#eef3f8' },
          textMuted: { value: '#9aa8b8' },
          textSubtle: { value: '#65727f' },
          // accents
          accent: { value: '#b8ff3c' },
          accentSoft: { value: '#2c4414' },
          live: { value: '#4dd8ff' },
          liveSoft: { value: '#123240' },
          danger: { value: '#ff6b5e' },
          dangerSoft: { value: '#3d1a17' },
          // table
          felt: { value: '#0f5c46' },
          feltLine: { value: '#1d7a5e' },
          cushion: { value: '#0a4231' },
          rail: { value: '#2a1b12' },
          railEdge: { value: '#432d1d' },
          pocket: { value: '#06090c' },
          diamond: { value: '#e2d3ae' },
          guide: { value: '#8e9cab' },
          // balls
          ballIvory: { value: '#f7f4ec' },
          ballPlate: { value: '#fbf8f0' },
          ballInk: { value: '#16181c' },
        },
        shadows: {
          card: { value: '0 8px 24px rgba(0, 0, 0, 0.45)' },
          glow: { value: '0 0 20px rgba(183, 255, 61, 0.35)' },
        },
      },
      keyframes: {
        rise: {
          from: { opacity: 0, transform: 'translateY(14px) scale(0.985)' },
          to: { opacity: 1, transform: 'none' },
        },
      },
      textStyles: {
        eyebrow: {
          value: {
            fontSize: '11px',
            lineHeight: '14px',
            fontWeight: '600',
            letterSpacing: '0.8px',
            textTransform: 'uppercase',
          },
        },
        body: { value: { fontSize: '13px', lineHeight: '19px', fontWeight: '400' } },
        control: { value: { fontSize: '13px', lineHeight: '16px', fontWeight: '500' } },
        name: { value: { fontSize: '14px', lineHeight: '20px', fontWeight: '600' } },
        cardTitle: { value: { fontSize: '16px', lineHeight: '22px', fontWeight: '600' } },
        section: {
          value: { fontSize: '20px', lineHeight: '26px', fontWeight: '600', letterSpacing: '-0.2px' },
        },
        pageTitle: {
          value: { fontSize: '26px', lineHeight: '32px', fontWeight: '700', letterSpacing: '-0.4px' },
        },
        stat: {
          value: { fontSize: '34px', lineHeight: '40px', fontWeight: '700', letterSpacing: '-0.8px' },
        },
      },
    },
  },
  outdir: 'styled-system',
})
