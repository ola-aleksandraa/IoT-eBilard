import type { AnalysisResult, Calibration, Settings } from './types'

export async function recognize(blob: Blob | null, settings: Settings, calibration: Calibration | null,
  frameId: string, signal: AbortSignal): Promise<AnalysisResult> {
  const options = { settings, calibration, client_frame_id: frameId }
  let body: FormData | string
  if (blob) {
    body = new FormData()
    body.append('file', blob, 'frame.png')
    body.append('config', JSON.stringify(options))
  } else body = JSON.stringify(options)
  const response = await fetch(`/api/v1/${blob ? 'images' : 'camera'}/detect`, {
    method: 'POST', body, signal, ...(blob ? {} : { headers: { 'Content-Type': 'application/json' } }),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Recognition returned HTTP ${response.status}`)
  }
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Expected numerical JSON from backend.')
  const result = await response.json() as AnalysisResult
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
    return { blob: canonical, frame: { image: URL.createObjectURL(canonical), width: canvas.width, height: canvas.height, name, synthetic } }
  } finally { bitmap.close() }
}
