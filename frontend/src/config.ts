// Runtime configuration. Override any value with a VITE_* env variable, e.g. in frontend/.env.local:
//   VITE_DETECT_INTERVAL_MS=5000
// or inline: `VITE_DETECT_INTERVAL_MS=5000 pnpm dev`. Values are read at dev-server start / build time.

function positiveInt(raw: string | undefined, fallback: number): number {
  const value = Number(raw)
  return raw && Number.isInteger(value) && value > 0 ? value : fallback
}

/** How often the table view asks the Raspberry Pi for a fresh camera detection (ms). */
export const DETECT_INTERVAL_MS = positiveInt(import.meta.env.VITE_DETECT_INTERVAL_MS, 7000)
