import { useCallback, useEffect, useRef, useState } from 'react'
import { localFrame, recognize } from './api'
import SourceView from './SourceView'
import TableCanvas from './TableCanvas'
import { useCamera } from './useCamera'
import { BALL_NAMES, DEFAULT_SETTINGS, type AnalysisResult, type Calibration, type Frame, type Point } from './types'

export default function App() {
  const camera = useCamera()
  const [frame, setFrame] = useState<Frame | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('Choose a local image, browser camera or server camera.')
  const [busy, setBusy] = useState(false)
  const [auto, setAuto] = useState(false)
  const [mode, setMode] = useState<'image' | 'browser' | 'server'>('image')
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [locked, setLocked] = useState(false)
  const [manual, setManual] = useState(false)
  const [corners, setCorners] = useState<Point[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const image = useRef<Blob | null>(null)
  const active = useRef<AbortController | null>(null)
  const sequence = useRef(0)
  const slot = useRef(false)
  const calibration = useRef<Calibration | null>(null)
  const preview = useRef<string | null>(null)
  const generation = useRef(0)

  const clear = useCallback(() => {
    generation.current++; active.current?.abort(); setResult(null); setSelected(null)
    calibration.current = null; setLocked(false); setManual(false); setCorners([]); setAuto(false); setError('')
  }, [])
  const showFrame = useCallback((next: Frame) => {
    if (preview.current) URL.revokeObjectURL(preview.current)
    preview.current = next.image; setFrame(next)
  }, [])
  useEffect(() => () => { active.current?.abort(); if (preview.current) URL.revokeObjectURL(preview.current) }, [])
  useEffect(() => {
    if (mode === 'browser' && !camera.stream) { clear(); setStatus('Browser camera disconnected.'); }
  }, [camera.stream, mode, clear])

  const load = async (blob: Blob, name: string, synthetic = false) => {
    clear(); camera.stop(); setMode('image'); setStatus('Decoding local image…')
    const epoch = generation.current
    try {
      const next = await localFrame(blob, name, synthetic)
      if (epoch !== generation.current) { URL.revokeObjectURL(next.frame.image); return }
      image.current = next.blob; showFrame(next.frame); setStatus('Image ready. Run recognition.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
  }
  const run = useCallback(async () => {
    if (slot.current) return
    slot.current = true; setBusy(true); setError('')
    const controller = new AbortController(); active.current = controller
    const epoch = generation.current
    const token = String(++sequence.current)
    try {
      let blob = mode === 'image' ? image.current : null
      if (mode === 'image' && !blob) throw new Error('Choose a source image first.')
      if (mode === 'browser') {
        const video = camera.video.current
        if (!camera.stream || !video || video.readyState < 2) throw new Error('Connect a browser camera and wait for video.')
        const canvas = document.createElement('canvas')
        const scale = Math.min(1, 1280 / video.videoWidth, 960 / video.videoHeight)
        canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale)
        canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height)
        blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Frame capture failed.')), 'image/jpeg', .92))
        showFrame({ image: URL.createObjectURL(blob), width: canvas.width, height: canvas.height, name: 'Browser camera frame', synthetic: false })
      }
      if (epoch !== generation.current || controller.signal.aborted) return
      const output = await recognize(blob, settings, locked ? calibration.current : null, token, controller.signal)
      if (epoch !== generation.current || controller.signal.aborted) return
      setResult(output); setSelected(null)
      setStatus(output.detection ? `${output.detection.counts.total} balls · ${output.analysis_ms.toFixed(1)} ms analysis · numerical JSON` : 'Looking for table. Previous positions cleared.')
    } catch (reason) {
      if (epoch !== generation.current || controller.signal.aborted) return
      setResult(null); setError(reason instanceof Error ? reason.message : String(reason)); setStatus('Recognition failed. Previous positions cleared.')
    } finally {
      slot.current = false; setBusy(false)
    }
  }, [mode, camera.stream, camera.video, settings, locked, showFrame])

  useEffect(() => {
    if (!auto) return
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => { await run(); if (!disposed) timer = setTimeout(() => void tick(), 750) }
    void tick()
    return () => { disposed = true; clearTimeout(timer); active.current?.abort() }
  }, [auto, run])

  const balls = result?.detection?.balls ?? []
  const detail = balls.find(ball => ball.id === selected)
  return <main>
    <header><div><p className="eyebrow">IoT-eBilard / integration PoC</p><h1>Ball / Verify</h1><p>Local pixels in. Numerical recognition out. This client draws every ball.</p></div>
      <a href="http://127.0.0.1:8001/docs" target="_blank" rel="noreferrer">Backend API docs ↗</a></header>
    <section className="toolbar" aria-label="Source controls">
      <button disabled={busy} onClick={() => void fetch('/sample-table.png').then(response => { if (!response.ok) throw new Error('Sample unavailable'); return response.blob() }).then(blob => load(blob, 'Local synthetic fixture', true)).catch(reason => setError(String(reason)))}>Load local sample</button>
      <button disabled={busy} onClick={() => void fetch('/empty-table.png').then(response => response.blob()).then(blob => load(blob, 'Local blank fixture', true))}>Load blank frame</button>
      <label className="file">Upload photo<input aria-label="Upload photo" type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void load(file, file.name); event.target.value = '' }} /></label>
      <select aria-label="Browser camera" value={camera.deviceId} onChange={event => { clear(); setMode('browser'); camera.setDeviceId(event.target.value); void camera.connect(event.target.value) }}>
        <option value="">Default camera</option>{camera.devices.map(device => <option key={device.deviceId} value={device.deviceId}>{device.label || device.deviceId}</option>)}
      </select>
      <button disabled={busy || camera.connecting} onClick={() => { clear(); setMode('browser'); image.current = null; setFrame(null); void camera.connect(camera.deviceId) }}>Connect browser camera</button>
      <button onClick={() => { camera.stop(); clear(); setStatus('Camera disconnected.') }}>Disconnect</button>
      <button disabled={busy} onClick={() => { clear(); camera.stop(); setMode('server'); image.current = null; setFrame(null); setStatus('Server-camera mode. Recognition returns JSON only.') }}>Use server camera</button>
    </section>
    <section className="toolbar" aria-label="Recognition controls">
      <button className="primary" disabled={busy || manual} onClick={() => void run()}>{busy ? 'Recognizing…' : 'Recognize frame'}</button>
      <label><input type="checkbox" checked={auto} disabled={mode === 'image' || manual} onChange={event => setAuto(event.target.checked)} />Sequential live updates</label>
      <label>Table width / height<input aria-label="Table ratio" type="number" min="1" max="3" step="0.1" value={settings.table_ratio} disabled={busy || auto} onChange={event => { clear(); setSettings({ ...settings, table_ratio: Math.min(3, Math.max(1, Number(event.target.value))) }) }} /></label>
      <label>Radius / table height<input aria-label="Ball radius" type="number" min="0.012" max="0.06" step="0.001" value={settings.ball_radius_ratio} disabled={busy || auto} onChange={event => { clear(); setSettings({ ...settings, ball_radius_ratio: Math.min(.06, Math.max(.012, Number(event.target.value))) }) }} /></label>
      <button disabled={!result?.calibration || busy} onClick={() => { calibration.current = result!.calibration; setLocked(true) }}>Reuse detected corners</button>
      <button disabled={!frame || busy || mode === 'server' || auto} onClick={() => { setManual(true); setCorners([]); setStatus('Click four inner-cushion corners clockwise; first edge along long side.') }}>Set corners manually</button>
      {manual && <button disabled={corners.length !== 4 || !frame} onClick={() => { calibration.current = { corners, image_width: frame!.width, image_height: frame!.height }; setLocked(true); setManual(false); setStatus('Manual calibration ready.') }}>Apply four corners</button>}
      <button disabled={busy} onClick={() => { clear(); setStatus('Automatic calibration enabled.') }}>Reset calibration</button>
      <span className="badge">{locked ? 'Corners fixed' : 'Automatic corners'}</span>
    </section>
    <p role="status">{status}</p>{(error || camera.error) && <p role="alert">{error || camera.error}</p>}
    <div className="views"><section className="panel"><h2>Source · local camera or upload</h2>
      <video ref={camera.video} hidden={mode !== 'browser' || !camera.stream} muted autoPlay playsInline aria-label="Browser camera preview" />
      {frame ? <SourceView frame={frame} corners={manual ? corners : result?.calibration?.corners ?? []} editing={manual} onCorners={setCorners} balls={balls} selected={selected} onSelect={setSelected} showLabels /> : <div className="empty">{mode === 'server' ? 'Server pixels stay in the backend. Only its numerical results reach this client.' : 'Load a photo or connect your camera.'}</div>}
    </section><section className="panel"><h2>2D table · drawn from JSON in this browser</h2><div className="table-wrap"><TableCanvas balls={balls} ratio={result?.detection?.geometry.table_ratio ?? settings.table_ratio} selected={selected} onSelect={setSelected} showLabels showGrid /></div>
      <div className="legend">{Object.entries(BALL_NAMES).map(([kind, label]) => <span key={kind}>{label}: {result?.detection?.counts[kind as keyof typeof BALL_NAMES] ?? 0}</span>)}</div>
      <p className="formula">center = (x × W, y × H) · radius = r × H · W / H = table_ratio</p>
    </section></div>
    <section className="panel"><h2>Coordinates and decision evidence</h2><div className="scroll"><table><thead><tr><th>Frame ID</th><th>Type</th><th>x</th><th>y</th><th>Radius / H</th><th>Rule score</th><th>Method</th></tr></thead><tbody>{balls.map(ball => <tr key={ball.id} onClick={() => setSelected(ball.id)}><td>{ball.id}</td><td>{BALL_NAMES[ball.kind]}</td><td>{ball.x.toFixed(5)}</td><td>{ball.y.toFixed(5)}</td><td>{ball.radius}</td><td>{ball.confidence}</td><td>{ball.method}</td></tr>)}</tbody></table></div>
      {detail && <p>{detail.reason}</p>}{result?.detection?.warnings.map(warning => <p className="warning" key={warning}>{warning}</p>)}
      <details><summary>Inspect numerical API response</summary><pre data-testid="api-result">{result ? JSON.stringify(result, null, 2) : 'No response yet.'}</pre></details>
    </section>
    <footer>Verification client based on the first PoC. Sample fixtures are served by Vite. The root FastAPI service provides no images or demo endpoints. Rule scores and camera accuracy require validation for your scene.</footer>
  </main>
}
