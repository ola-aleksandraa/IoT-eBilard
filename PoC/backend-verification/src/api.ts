import type { AnalysisResult, Calibration, Settings } from './types'

// Share the backend's single processing lane between frames and shot requests.
let processing: Promise<unknown> = Promise.resolve()

function request<T>(path: string, init: RequestInit): Promise<T> {
  const signal = init.signal
    ? AbortSignal.any([init.signal, AbortSignal.timeout(60000)])
    : AbortSignal.timeout(60000)
  const next = processing.then(() => performRequest<T>(path, { ...init, signal }))
  processing = next.catch(() => {})
  return next
}

function pause(ms: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted()
  return new Promise((resolve, reject) => {
    const done = () => { signal.removeEventListener('abort', abort); resolve() }
    const timer = setTimeout(done, ms)
    const abort = () => { clearTimeout(timer); reject(signal.reason) }
    signal.addEventListener('abort', abort, { once: true })
  })
}

async function performRequest<T>(path: string, init: RequestInit & { signal: AbortSignal }): Promise<T> {
  init.signal.throwIfAborted()
  let response: Response
  try {
    for (let attempt = 0; ; attempt++) {
      response = await fetch(`/api/v1${path}`, init)
      // Aborting HTTP does not stop an OpenCV call already running server-side.
      // Retry explicit admission-control responses, never camera failures.
      if (response.status !== 503 || !response.headers.has('Retry-After') || attempt >= 2) break
      await pause(Math.min(5, Math.max(1, Number(response.headers.get('Retry-After')) || 1)) * 1000, init.signal)
    }
  }
  catch (error) {
    if (init.signal?.aborted) throw error
    throw new Error('Cannot reach the detection service. Start the Python backend on port 8001, then try again.')
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Recognition returned HTTP ${response.status}`)
  }
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Expected numerical JSON from backend.')
  return response.json() as Promise<T>
}

export function jsonRequest<T>(path: string, init: RequestInit): Promise<T> { return request<T>(path, init) }

export async function recognize(blob: Blob | null, settings: Settings, calibration: Calibration | null,
  frameId: string, signal: AbortSignal): Promise<AnalysisResult> {
  const options = { settings, calibration, client_frame_id: frameId }
  let body: FormData | string
  if (blob) {
    body = new FormData()
    body.append('file', blob, 'frame.png')
    body.append('config', JSON.stringify(options))
  } else body = JSON.stringify(options)
  const result = await request<AnalysisResult>(`/${blob ? 'images' : 'camera'}/detect`, {
    method: 'POST', body, signal, ...(blob ? {} : { headers: { 'Content-Type': 'application/json' } }),
  })
  if (result.schema_version !== '1.0' || result.client_frame_id !== frameId) throw new Error('Unexpected API version or frame correlation.')
  return result
}

export async function localFrame(blob: Blob, name: string, synthetic = false) {
  // Orient once locally and send exactly the same pixels shown in SourceView.
  const bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' })
  try {
    if (Math.min(bitmap.width, bitmap.height) < 100 || Math.max(bitmap.width, bitmap.height) > 10000 || bitmap.width * bitmap.height > 16_000_000) {
      throw new Error('Use an image of at least 100 pixels per side and at most 16 megapixels / 10,000 pixels per side.')
    }
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width; canvas.height = bitmap.height
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0)
    const canonical = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Cannot decode source frame.')), 'image/png'))
    if (canonical.size > 12 * 1024 * 1024) throw new Error('The decoded image exceeds 12 MiB. Choose a smaller photo.')
    return { blob: canonical, frame: { image: URL.createObjectURL(canonical), width: canvas.width, height: canvas.height, name, synthetic } }
  } finally { bitmap.close() }
}
