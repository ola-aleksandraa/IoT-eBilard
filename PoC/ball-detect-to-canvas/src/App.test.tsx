// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { LiveResponse } from './types'

const mocks = vi.hoisted(() => ({ api: vi.fn(), video: { current: null }, stream: {} as MediaStream | null }))
vi.mock('./types', async importOriginal => ({ ...await importOriginal<typeof import('./types')>(), api: mocks.api }))
vi.mock('./TableCanvas', () => ({ default: ({ balls }: { balls: unknown[] }) => <div data-testid="canvas-count">{balls.length}</div> }))
vi.mock('./useCamera', () => ({ useCamera: () => ({ video: mocks.video, stream: mocks.stream, devices: [], deviceId: '', connecting: false, error: '', stop: vi.fn(), connect: vi.fn(), setDeviceId: vi.fn(), setError: vi.fn(), refresh: vi.fn() }) }))
import App from './App'

beforeEach(() => {
  vi.useFakeTimers(); mocks.api.mockReset(); mocks.stream = {} as MediaStream
  Object.defineProperties(HTMLVideoElement.prototype, { readyState: { configurable: true, get: () => 4 }, videoWidth: { configurable: true, get: () => 1280 }, videoHeight: { configurable: true, get: () => 720 } })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback => callback(new Blob(['frame'], { type: 'image/jpeg' })))
  HTMLDialogElement.prototype.close = vi.fn(); HTMLDialogElement.prototype.showModal = vi.fn()
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })

const found: LiveResponse = { table_status: 'detected', calibration: { image_width: 1280, image_height: 720, corners: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }] }, detection: { balls: [{ id: 1, kind: 'cue', x: .3, y: .4, radius: .026, source_x: .3, source_y: .4, color: '#ffffff', confidence: .9, reason: 'White', white_fraction: .9, method: 'contour' }], table: { width: 1000, height: 500, ratio: 2 }, images: null, cloth_hue: 80, processing_ms: 20, warnings: [], homography: [], coordinate_system: 'normalized' } }

function renderUnstable() {
  const view = render(<App />)
  fireEvent.click(screen.getByRole('switch', { name: 'Camera is unstable' }))
  return view
}

it('waits for each frame, maps results, and clears the canvas when the table disappears', async () => {
  let resolveFirst!: (value: LiveResponse) => void
  mocks.api.mockReturnValueOnce(new Promise<LiveResponse>(resolve => { resolveFirst = resolve }))
  mocks.api.mockResolvedValueOnce({ table_status: 'searching', calibration: null, detection: null })
  renderUnstable()
  await act(async () => {})
  expect(mocks.api).toHaveBeenCalledTimes(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  expect(mocks.api).toHaveBeenCalledTimes(1)
  await act(async () => { resolveFirst(found) })
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  expect(screen.getByRole('status').textContent).toContain('updating table corners live')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(mocks.api).toHaveBeenCalledTimes(2)
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
  expect(screen.getByRole('status').textContent).toContain('Looking for the table')
})

it('aborts a pending frame and clears detections when the camera disconnects', async () => {
  mocks.api.mockResolvedValueOnce(found).mockReturnValueOnce(new Promise(() => {}))
  const { rerender } = renderUnstable()
  await act(async () => {})
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  const signal = mocks.api.mock.calls[1][1].signal as AbortSignal
  mocks.stream = null; rerender(<App />)
  expect(signal.aborted).toBe(true)
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
})

it('clears an old layout on API failure and recovers on a later frame', async () => {
  mocks.api.mockResolvedValueOnce(found).mockRejectedValueOnce(new Error('Service unavailable')).mockResolvedValueOnce(found)
  renderUnstable()
  await act(async () => {})
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
  expect(screen.getByRole('alert').textContent).toContain('Service unavailable')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  expect(screen.queryByRole('alert')).toBeNull()
})


it('defaults to fixed-camera consensus, locks corners, then recalibrates on request', async () => {
  mocks.api.mockResolvedValue(found)
  render(<App />)
  expect((screen.getByRole('switch', { name: 'Camera is unstable' }) as HTMLInputElement).checked).toBe(false)
  await act(async () => {})
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
  for (let i = 0; i < 7; i++) await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(mocks.api).toHaveBeenCalledTimes(8)
  expect(screen.getByRole('status').textContent).toContain('Corners locked')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  const lockedConfig = JSON.parse((mocks.api.mock.calls[8][1].body as FormData).get('config') as string)
  expect(lockedConfig.calibration).toEqual(found.calibration)
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  fireEvent.click(screen.getByRole('button', { name: 'Recalibrate corners' }))
  await act(async () => {})
  const latestConfig = JSON.parse((mocks.api.mock.lastCall![1].body as FormData).get('config') as string)
  expect(latestConfig.calibration).toBeNull()
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
})

it('switching to unstable mode resumes automatic corner updates', async () => {
  mocks.api.mockResolvedValue(found)
  render(<App />)
  await act(async () => {})
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  expect(JSON.parse((mocks.api.mock.lastCall![1].body as FormData).get('config') as string).calibration).not.toBeNull()
  fireEvent.click(screen.getByRole('switch', { name: 'Camera is unstable' }))
  await act(async () => {})
  expect(JSON.parse((mocks.api.mock.lastCall![1].body as FormData).get('config') as string).calibration).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('updating table corners live')
})
