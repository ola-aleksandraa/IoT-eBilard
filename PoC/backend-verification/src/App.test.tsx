// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { DEFAULT_SETTINGS, type AnalysisResult } from './types'

const mocks = vi.hoisted(() => ({ recognize: vi.fn(), localFrame: vi.fn() }))
vi.mock('./api', () => mocks)
vi.mock('./TableCanvas', () => ({ default: ({ balls }: { balls: unknown[] }) => <div data-testid="rendered-balls">{balls.length}</div> }))
vi.mock('./SourceView', () => ({ default: () => <div>Local source preview</div> }))
vi.mock('./useCamera', () => ({ useCamera: () => ({ video: { current: null }, stream: null, devices: [], deviceId: '', connecting: false, error: '', stop: vi.fn(), connect: vi.fn(), setDeviceId: vi.fn() }) }))
import App from './App'

const found: AnalysisResult = { schema_version: '1.0', frame_id: 'server-frame-1', client_frame_id: '1', table_status: 'detected', settings: DEFAULT_SETTINGS,
  source: { kind: 'upload', width: 1200, height: 760, acquired_at: '2026-10-23T08:00:00Z', lens_corrected: false },
  calibration: { image_width: 1200, image_height: 760, corners: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }] },
  detection: { balls: [{ id: 1, kind: 'cue', x: .2, y: .3, radius: .026, source_x: .2, source_y: .3, confidence: .9, white_fraction: .9, reason: 'White', method: 'contour' }],
    counts: { total: 1, cue: 1, eight: 0, solid: 0, striped: 0, unknown: 0 },
    geometry: { table_ratio: 2, source_to_table: [[1 / 1199, 0, 0], [0, 1 / 759, 0], [0, 0, 1]],
      table_to_source: [[1199, 0, 0], [0, 759, 0], [0, 0, 1]], origin: 'top_left', x_direction: 'right', y_direction: 'down',
      center_unit: 'normalized_table', radius_unit: 'table_height', source_space: 'oriented_pixels' },
    cloth_hue: 80, processing_ms: 10, warnings: [] }, analysis_ms: 20 }

beforeEach(() => {
  mocks.recognize.mockReset(); mocks.localFrame.mockReset()
  mocks.localFrame.mockResolvedValue({ blob: new Blob(['local']), frame: { image: 'blob:local', width: 1200, height: 760, name: 'sample', synthetic: true } })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['sample']) }))
  vi.stubGlobal('URL', { revokeObjectURL: vi.fn() })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

async function loadSample() {
  fireEvent.click(screen.getByRole('button', { name: 'Load local sample' }))
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Image ready'))
}

it('loads fixture locally and draws numerical backend results', async () => {
  mocks.recognize.mockResolvedValue(found)
  render(<App />); await loadSample()
  expect(mocks.recognize).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Recognize frame' }))
  await waitFor(() => expect(screen.getByTestId('rendered-balls').textContent).toBe('1'))
  expect(screen.getByTestId('api-result').textContent).toContain('"x": 0.2')
  expect(mocks.recognize.mock.calls[0][0]).toBeInstanceOf(Blob)
})

it('clears previous detections on table loss and backend failure', async () => {
  mocks.recognize.mockResolvedValueOnce(found).mockResolvedValueOnce({ ...found, table_status: 'searching', calibration: null, detection: null }).mockRejectedValueOnce(new Error('Service unavailable'))
  render(<App />); await loadSample()
  fireEvent.click(screen.getByRole('button', { name: 'Recognize frame' }))
  await waitFor(() => expect(screen.getByTestId('rendered-balls').textContent).toBe('1'))
  fireEvent.click(screen.getByRole('button', { name: 'Recognize frame' }))
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Looking for table'))
  expect(screen.getByTestId('rendered-balls').textContent).toBe('0')
  fireEvent.click(screen.getByRole('button', { name: 'Recognize frame' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Service unavailable'))
  expect(screen.getByTestId('rendered-balls').textContent).toBe('0')
})

it('aborts and ignores a late response after resetting the source state', async () => {
  let finish!: (result: AnalysisResult) => void
  mocks.recognize.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  render(<App />); await loadSample()
  fireEvent.click(screen.getByRole('button', { name: 'Recognize frame' }))
  await waitFor(() => expect(mocks.recognize).toHaveBeenCalledTimes(1))
  const signal = mocks.recognize.mock.calls[0][4] as AbortSignal
  fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }))
  expect(signal.aborted).toBe(true)
  await act(async () => finish(found))
  expect(screen.getByTestId('rendered-balls').textContent).toBe('0')
})
