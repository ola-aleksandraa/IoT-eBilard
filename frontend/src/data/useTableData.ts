import { useEffect, useState } from 'react'
import { DETECT_INTERVAL_MS } from '../config'
import { detectCamera, suggestShot } from './api'
import { buildHistory } from './history'
import { hintShot, history as mockHistory, predictedShot } from './mock'
import type { ShotSuggestion, TableSnapshot } from './types'

export type DataSource = 'mock' | 'backend'

export interface TableData {
  source: DataSource
  history: TableSnapshot[]
  /** Path for the current aim. The backend has no aim input yet, so only the mock has one. */
  predicted: ShotSuggestion | null
  /** Shot revealed by "Pomóż mi". */
  hint: ShotSuggestion | null
}

const MOCK: TableData = { source: 'mock', history: mockHistory, predicted: predictedShot, hint: hintShot }

// Until the first successful detection, retry quickly – covers the first `uv run` installing the environment.
const STARTUP_RETRY_MS = 2000
const STARTUP_ATTEMPTS = 20 // ~40 s

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const id = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => (clearTimeout(id), reject(signal.reason)), { once: true })
  })

/**
 * Ball layout for the table view. Starts with the mock, switches to the Raspberry Pi's camera
 * detection as soon as it answers, then polls it every DETECT_INTERVAL_MS (sequentially – the
 * next request starts only after the previous one finished). A failed poll keeps the last layout.
 * The shot hint (website backend) is optional.
 */
export function useTableData(): TableData {
  const [data, setData] = useState<TableData>(MOCK)

  useEffect(() => {
    const ctrl = new AbortController()
    const { signal } = ctrl
    ;(async () => {
      let connected = false
      let failures = 0
      while (!signal.aborted) {
        try {
          const balls = await detectCamera(signal)
          const hint = await suggestShot(balls, signal).catch(() => null)
          setData({ source: 'backend', history: buildHistory(balls), predicted: null, hint })
          connected = true
          failures = 0
        } catch (err) {
          if (signal.aborted) return
          failures++
          if (connected) console.warn('[eBilard] detection failed, keeping the last layout', err)
          else if (failures === STARTUP_ATTEMPTS) console.info('[eBilard] backend unavailable, staying on mock data', err)
        }
        const startingUp = !connected && failures < STARTUP_ATTEMPTS
        await sleep(startingUp ? STARTUP_RETRY_MS : DETECT_INTERVAL_MS, signal)
      }
    })().catch(() => {})
    return () => ctrl.abort()
  }, [])

  return data
}
