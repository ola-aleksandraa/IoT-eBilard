// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AnalysisResult } from './types'

const mocks = vi.hoisted(() => ({ recognize: vi.fn(), jsonRequest: vi.fn(), localFrame: vi.fn(), video: { current: null }, stream: {} as MediaStream | null }))
vi.mock('./api', async importOriginal => ({ ...await importOriginal<typeof import('./api')>(), recognize: mocks.recognize, jsonRequest: mocks.jsonRequest, localFrame: mocks.localFrame }))
vi.mock('./TableCanvas', () => ({ default: ({ balls, aimMode, onAim }: { balls: unknown[]; aimMode: boolean; onAim: (point: { x: number; y: number }) => void }) => <div><div data-testid="canvas-count">{balls.length}</div>{aimMode && <button onClick={() => onAim({ x: .8, y: .4 })}>Aim at object</button>}</div> }))
vi.mock('./useCamera', () => ({ useCamera: () => ({ video: mocks.video, stream: mocks.stream, devices: [], deviceId: '', connecting: false, error: '', stop: vi.fn(), connect: vi.fn(), setDeviceId: vi.fn(), setError: vi.fn(), refresh: vi.fn() }) }))
import App from './App'

beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear(); mocks.recognize.mockReset(); mocks.jsonRequest.mockReset(); mocks.localFrame.mockReset(); mocks.stream = {} as MediaStream
  Object.defineProperties(HTMLVideoElement.prototype, { readyState: { configurable: true, get: () => 4 }, videoWidth: { configurable: true, get: () => 1280 }, videoHeight: { configurable: true, get: () => 720 } })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback => callback(new Blob(['frame'], { type: 'image/jpeg' })))
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['photo']) }))
  mocks.localFrame.mockResolvedValue({ blob: new Blob(['photo']), frame: { image: 'data:image/png;base64,cGhvdG8=', width: 1280, height: 720, name: 'photo', synthetic: true } })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

const found: AnalysisResult = { schema_version: '1.0', frame_id: 'test', client_frame_id: '1',
  source: { kind: 'upload', width: 1280, height: 720, acquired_at: '2026-10-26T12:00:00Z', lens_corrected: false },
  settings: { table_ratio: 2, ball_radius_ratio: .026, cloth_hue: null, hue_tolerance: 16, saturation_min: 55, split_touching: true }, analysis_ms: 25,
  table_status: 'detected', calibration: { image_width: 1280, image_height: 720, corners: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }] },
  detection: { balls: [{ id: 1, kind: 'cue', x: .3, y: .4, radius: .026, source_x: .3, source_y: .4, confidence: .9, reason: 'White', white_fraction: .9, method: 'contour' }],
    counts: { total: 1, cue: 1, eight: 0, solid: 0, striped: 0, unknown: 0 },
    geometry: { table_ratio: 2, source_to_table: [], table_to_source: [], origin: 'top_left', x_direction: 'right', y_direction: 'down', center_unit: 'normalized_table', radius_unit: 'table_height', source_space: 'oriented_pixels' },
    cloth_hue: 80, processing_ms: 20, warnings: [] } }

function renderUnstable() {
  const view = render(<App />)
  fireEvent.click(screen.getByRole('switch', { name: 'Camera is unstable' }))
  return view
}

it('waits for each frame, maps results, and clears the canvas when the table disappears', async () => {
  let resolveFirst!: (value: AnalysisResult) => void
  mocks.recognize.mockReturnValueOnce(new Promise<AnalysisResult>(resolve => { resolveFirst = resolve }))
  mocks.recognize.mockResolvedValueOnce({ table_status: 'searching', calibration: null, detection: null })
  renderUnstable()
  await act(async () => {})
  expect(mocks.recognize).toHaveBeenCalledTimes(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  expect(mocks.recognize).toHaveBeenCalledTimes(1)
  await act(async () => { resolveFirst(found) })
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  expect(screen.getByRole('status').textContent).toContain('updating table corners live')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(mocks.recognize).toHaveBeenCalledTimes(2)
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
  expect(screen.getByRole('status').textContent).toContain('Looking for the table')
})

it('aborts a pending frame and clears detections when the camera disconnects', async () => {
  mocks.recognize.mockResolvedValueOnce(found).mockReturnValueOnce(new Promise(() => {}))
  const { rerender } = renderUnstable()
  await act(async () => {})
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  const signal = mocks.recognize.mock.calls[1][4] as AbortSignal
  mocks.stream = null; rerender(<App />)
  expect(signal.aborted).toBe(true)
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
})

it('clears an old layout on API failure and recovers on a later frame', async () => {
  mocks.recognize.mockResolvedValueOnce(found).mockRejectedValueOnce(new Error('Service unavailable')).mockResolvedValueOnce(found)
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
  mocks.recognize.mockResolvedValue(found)
  render(<App />)
  expect((screen.getByRole('switch', { name: 'Camera is unstable' }) as HTMLInputElement).checked).toBe(false)
  await act(async () => {})
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
  for (let i = 0; i < 7; i++) await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(mocks.recognize).toHaveBeenCalledTimes(8)
  expect(screen.getByRole('status').textContent).toContain('Corners locked')
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  const lockedConfig = { calibration: mocks.recognize.mock.calls[8][2] }
  expect(lockedConfig.calibration).toEqual(found.calibration)
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  fireEvent.click(screen.getByRole('button', { name: 'Recalibrate corners' }))
  await act(async () => {})
  const latestConfig = { calibration: mocks.recognize.mock.lastCall![2] }
  expect(latestConfig.calibration).toBeNull()
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
})

it('switching to unstable mode resumes automatic corner updates', async () => {
  mocks.recognize.mockResolvedValue(found)
  render(<App />)
  await act(async () => {})
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  expect({ calibration: mocks.recognize.mock.lastCall![2] }.calibration).not.toBeNull()
  fireEvent.click(screen.getByRole('switch', { name: 'Camera is unstable' }))
  await act(async () => {})
  expect({ calibration: mocks.recognize.mock.lastCall![2] }.calibration).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('updating table corners live')
})


it('loads and recognizes a local photo immediately and reapplies saved corners to it', async () => {
  mocks.stream = null
  mocks.recognize.mockResolvedValue(found)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Try a sample image' }))
  await act(async () => {})
  expect(mocks.localFrame).toHaveBeenCalled()
  expect(mocks.recognize.mock.calls[0][0]).toBeInstanceOf(Blob)
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save current corners' }))
  fireEvent.click(screen.getByRole('button', { name: 'Use saved corners' }))
  await act(async () => {})
  expect(mocks.recognize.mock.lastCall![2]).toEqual(found.calibration)
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
})

it('uploads a photo from settings and clears the old layout on failure', async () => {
  mocks.stream = null
  mocks.recognize.mockResolvedValueOnce(found).mockRejectedValueOnce(new Error('Bad photo'))
  render(<App />)
  fireEvent.change(screen.getByLabelText('Upload table photo'), { target: { files: [new File(['photo'], 'table.png', { type: 'image/png' })] } })
  await act(async () => {})
  expect(mocks.localFrame.mock.calls[0][1]).toBe('table.png')
  expect(screen.getByTestId('canvas-count').textContent).toBe('1')
  fireEvent.change(screen.getByLabelText('Upload table photo'), { target: { files: [new File(['bad'], 'bad.png', { type: 'image/png' })] } })
  await act(async () => {})
  expect(screen.getByRole('alert').textContent).toContain('Bad photo')
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
})

it('requests and displays shot suggestions, then simulates a cue aim', async () => {
  mocks.stream = null
  mocks.recognize.mockResolvedValue(found)
  const shot = { target_ball_id: 2, pocket: 2, shot_type: 'direct', score: .8, cue_path: [], target_path: [], cue_deflect_path: [] }
  mocks.jsonRequest.mockResolvedValueOnce({ status: 'ok', cue_ball_id: 1, shots: [shot], blocked: [] })
    .mockResolvedValueOnce({ status: 'ok', cue_ball_id: 1, first_ball_id: 2, duration: 0, dt: .025, balls: [], events: [{ type: 'contact', with: 1, ball: 2, t: .5 }], potted: [] })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Try a sample image' }))
  await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Show shot predictions' }))
  fireEvent.click(screen.getByRole('button', { name: 'Close settings' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(300) })
  expect(mocks.jsonRequest.mock.calls[0][0]).toBe('/shots')
  expect(JSON.parse(mocks.jsonRequest.mock.calls[0][1].body).balls).toEqual(found.detection!.balls)
  expect(screen.getByRole('button', { name: /Direct · ball 2/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Aim cue' }))
  fireEvent.click(screen.getByRole('button', { name: 'Aim at object' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(100) })
  expect(mocks.jsonRequest.mock.calls[1][0]).toBe('/shots/simulate')
  expect(JSON.parse(mocks.jsonRequest.mock.calls[1][1].body)).toMatchObject({ aim_x: .8, aim_y: .4, table_ratio: 2 })
  expect(screen.getByLabelText('Cue prediction').textContent).toContain('Ball 2 hit at 0.50 s')
})


it('waits for usable camera pixels instead of uploading a privacy placeholder', async () => {
  Object.defineProperties(HTMLVideoElement.prototype, {
    videoWidth: { configurable: true, get: () => 2 }, videoHeight: { configurable: true, get: () => 2 },
  })
  renderUnstable()
  await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  expect(mocks.recognize).not.toHaveBeenCalled()
  expect(screen.getByRole('status').textContent).toContain('Waiting for camera frames')
})

it('applies measured table dimensions and cloth controls to photo recognition and shot geometry', async () => {
  mocks.stream = null
  mocks.recognize.mockResolvedValue(found)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Try a sample image' }))
  await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
  fireEvent.change(screen.getByLabelText('Cloth length'), { target: { value: '210' } })
  fireEvent.change(screen.getByLabelText('Cloth width'), { target: { value: '100' } })
  fireEvent.change(screen.getByLabelText('Ball diameter'), { target: { value: '5.7' } })
  fireEvent.click(screen.getByRole('button', { name: 'Apply table dimensions' }))
  expect(screen.getByTestId('canvas-count').textContent).toBe('0')
  fireEvent.click(screen.getByRole('checkbox', { name: 'Detect cloth color automatically' }))
  fireEvent.change(screen.getByRole('slider', { name: 'Cloth hue' }), { target: { value: '65' } })
  fireEvent.change(screen.getByRole('slider', { name: 'Minimum cloth saturation' }), { target: { value: '40' } })
  const settings = { ...found.settings, table_ratio: 2.1, ball_radius_ratio: .0285, cloth_hue: 65, saturation_min: 40 }
  const detection = { ...found.detection!, balls: found.detection!.balls.map(ball => ({ ...ball, radius: .0285 })), geometry: { ...found.detection!.geometry, table_ratio: 2.1 } }
  mocks.recognize.mockResolvedValue({ ...found, settings, detection })
  mocks.jsonRequest.mockResolvedValue({ status: 'ok', cue_ball_id: 1, shots: [], blocked: [] })
  fireEvent.click(screen.getByRole('button', { name: 'Apply to image' }))
  await act(async () => {})
  expect(mocks.recognize.mock.lastCall![1]).toEqual(settings)
  fireEvent.click(screen.getByRole('checkbox', { name: 'Show shot predictions' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(300) })
  expect(JSON.parse(mocks.jsonRequest.mock.lastCall![1].body)).toMatchObject({ table_ratio: 2.1, balls: [{ radius: .0285 }] })
})

it('rejects invalid table measurements without changing the active detection settings', async () => {
  mocks.stream = null
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
  fireEvent.click(screen.getByRole('button', { name: 'Apply table dimensions' }))
  expect(screen.getByRole('alert').textContent).toContain('Enter positive measurements')
  expect(screen.getByText('2.00 : 1')).toBeTruthy()
})

it('refreshes shots when only the detected ball radius changes between live frames', async () => {
  const changed = { ...found, detection: { ...found.detection!, balls: found.detection!.balls.map(ball => ({ ...ball, radius: .031 })) } }
  mocks.recognize.mockResolvedValueOnce(found).mockResolvedValue(changed)
  mocks.jsonRequest.mockResolvedValue({ status: 'ok', cue_ball_id: 1, shots: [], blocked: [] })
  renderUnstable()
  await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Show shot predictions' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(300) })
  expect(mocks.jsonRequest).toHaveBeenCalledTimes(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(200) })
  await act(async () => { await vi.advanceTimersByTimeAsync(300) })
  expect(mocks.jsonRequest).toHaveBeenCalledTimes(2)
  expect(JSON.parse(mocks.jsonRequest.mock.lastCall![1].body).balls[0].radius).toBe(.031)
})
