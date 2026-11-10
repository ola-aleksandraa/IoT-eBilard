import { useEffect, useState } from 'react'
import { detectFrame, SAMPLE_FRAME_URL, suggestShot } from './api'
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

const RETRY_MS = 2000
const MAX_ATTEMPTS = 20 // ~40 s – covers the first `uv run` installing the environment

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const id = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => (clearTimeout(id), reject(signal.reason)), { once: true })
  })

/**
 * Ball layout for the table view. Starts with the mock and switches to the backend's
 * detection of the bundled test frame as soon as the backend answers.
 */
export function useTableData(): TableData {
  const [data, setData] = useState<TableData>(MOCK)

  useEffect(() => {
    const ctrl = new AbortController()
    const { signal } = ctrl
    ;(async () => {
      const frame = await fetch(SAMPLE_FRAME_URL, { signal }).then((r) => r.blob())
      for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        try {
          const balls = await detectFrame(frame, signal)
          const hint = await suggestShot(balls, signal).catch(() => null)
          setData({ source: 'backend', history: buildHistory(balls), predicted: null, hint })
          return
        } catch (err) {
          if (signal.aborted) return
          if (attempt === MAX_ATTEMPTS) console.info('[eBilard] backend unavailable, staying on mock data', err)
          else await sleep(RETRY_MS, signal)
        }
      }
    })().catch(() => {})
    return () => ctrl.abort()
  }, [])

  return data
}
