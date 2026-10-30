// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { jsonRequest, recognize } from './api'
import { DEFAULT_SETTINGS } from './types'

afterEach(() => vi.unstubAllGlobals())
const reply = (id: string) => new Response(JSON.stringify({ schema_version: '1.0', client_frame_id: id }), { headers: { 'Content-Type': 'application/json' } })

it('uploads pixels in multipart and asks only for numerical recognition', async () => {
  const fetcher = vi.fn().mockResolvedValue(reply('7'))
  vi.stubGlobal('fetch', fetcher)
  await recognize(new Blob(['frame']), DEFAULT_SETTINGS, null, '7', new AbortController().signal)
  const [path, options] = fetcher.mock.calls[0]
  expect(path).toBe('/api/v1/images/detect')
  expect(options.body).toBeInstanceOf(FormData)
  const config = JSON.parse(options.body.get('config'))
  expect(config).toEqual({ settings: DEFAULT_SETTINGS, calibration: null, client_frame_id: '7' })
  expect(config).not.toHaveProperty('debug')
})

it('server capture requires no image transfer to the client', async () => {
  const fetcher = vi.fn().mockResolvedValue(reply('8'))
  vi.stubGlobal('fetch', fetcher)
  await recognize(null, DEFAULT_SETTINGS, null, '8', new AbortController().signal)
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/camera/detect')
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toHaveProperty('client_frame_id', '8')
})

it('rejects an unexpected image response and mismatched frame response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('pixels', { headers: { 'Content-Type': 'image/png' } })).mockResolvedValueOnce(reply('different')))
  await expect(recognize(null, DEFAULT_SETTINGS, null, '9', new AbortController().signal)).rejects.toThrow('Expected numerical JSON')
  await expect(recognize(null, DEFAULT_SETTINGS, null, '9', new AbortController().signal)).rejects.toThrow('frame correlation')
})

it('reports a readable backend error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Another frame is processing.' }), { status: 503 })))
  await expect(recognize(null, DEFAULT_SETTINGS, null, '9', new AbortController().signal)).rejects.toThrow('Another frame is processing.')
})

it('serializes frames and shot requests through the same processing lane', async () => {
  let complete!: (response: Response) => void
  const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { complete = resolve }))
    .mockResolvedValueOnce(new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetcher)
  const frame = recognize(new Blob(['frame']), DEFAULT_SETTINGS, null, '10', new AbortController().signal)
  const shots = jsonRequest('/shots', { method: 'POST', body: '{}' })
  await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
  complete(reply('10'))
  await Promise.all([frame, shots])
  expect(fetcher.mock.calls.map(call => call[0])).toEqual(['/api/v1/images/detect', '/api/v1/shots'])
})

it('does not send a shot request cancelled while waiting behind a frame', async () => {
  let complete!: (response: Response) => void
  const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { complete = resolve }))
  vi.stubGlobal('fetch', fetcher)
  const frame = recognize(null, DEFAULT_SETTINGS, null, '11', new AbortController().signal)
  const controller = new AbortController()
  const shots = jsonRequest('/shots', { method: 'POST', signal: controller.signal })
  const cancelled = expect(shots).rejects.toThrow()
  await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
  controller.abort()
  complete(reply('11'))
  await frame; await cancelled
  expect(fetcher).toHaveBeenCalledTimes(1)
})

it('retries a busy processing slot but does not retry an unavailable camera', async () => {
  vi.useFakeTimers()
  try {
    const busy = () => new Response('{"detail":"busy"}', { status: 503, headers: { 'Retry-After': '1' } })
    const fetcher = vi.fn().mockResolvedValueOnce(busy()).mockResolvedValueOnce(reply('12'))
      .mockResolvedValueOnce(new Response('{"detail":"Camera unavailable"}', { status: 503 }))
    vi.stubGlobal('fetch', fetcher)
    const frame = recognize(null, DEFAULT_SETTINGS, null, '12', new AbortController().signal)
    await vi.advanceTimersByTimeAsync(1000)
    await frame
    await expect(recognize(null, DEFAULT_SETTINGS, null, '13', new AbortController().signal)).rejects.toThrow('Camera unavailable')
    expect(fetcher).toHaveBeenCalledTimes(3)
  } finally { vi.useRealTimers() }
})
