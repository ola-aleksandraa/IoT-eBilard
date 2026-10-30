import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownToLine, Camera, Check, ChevronDown, CircleDot, Crosshair, ImagePlus, Loader2, RefreshCw, Settings2, Square, Video, X } from 'lucide-react'
import TableCanvas from './TableCanvas'
import SourceView from './SourceView'
import TableSetup from './TableSetup'
import { useCamera } from './useCamera'
import { BallStabilizer, CornerConsensus } from './stability'
import { BALL_COLORS, BALL_NAMES, DEFAULT_SETTINGS, downloadJSON, POCKET_NAMES, SHOT_MESSAGES } from './types'
import { jsonRequest, localFrame, recognize } from './api'
import type { Calibration, Detection, Frame, MotionPrediction, Point, Settings, Shot, ShotsResponse } from './types'

const EMPTY_BALLS: Detection['balls'] = []
const EMPTY_SHOTS: Shot[] = []

export default function App() {
  const camera = useCamera()
  const [unstableCamera, setUnstableCamera] = useState(false)
  const [calibrationRevision, setCalibrationRevision] = useState(0)
  const [jitterTolerance, setJitterTolerance] = useState(0.006)
  const fixedCalibration = useRef<Calibration | null>(null)
  const consensus = useRef(new CornerConsensus())
  const stabilizer = useRef(new BallStabilizer())
  const session = useRef<{ stream: MediaStream | null; unstable: boolean; manual: Calibration | null; revision: number } | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [result, setResult] = useState<Detection | null>(null)
  const [frame, setFrame] = useState<Frame | null>(null)
  const [calibration, setCalibration] = useState<Calibration | null>(null)
  const [manual, setManual] = useState<Calibration | null>(null)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('Choose a camera to get started.')
  const [selected, setSelected] = useState<number | null>(null)
  const [updates, setUpdates] = useState(0)
  const [showIds, setShowIds] = useState(false)
  const [showGrid, setShowGrid] = useState(false)
  const [showShots, setShowShots] = useState(false)
  const [shotPlan, setShotPlan] = useState<ShotsResponse | null>(null)
  const [shotError, setShotError] = useState('')
  const [motionError, setMotionError] = useState('')
  const [activeShot, setActiveShot] = useState(0)
  const [aimMode, setAimMode] = useState(false)
  const [aim, setAim] = useState<Point | null>(null)
  const [motion, setMotion] = useState<MotionPrediction | null>(null)
  const [motionElapsed, setMotionElapsed] = useState(0)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 720 })
  const [saved, setSaved] = useState<Calibration | null>(() => {
    try {
      const c = JSON.parse(localStorage.getItem('live-table-calibration') ?? 'null') as Calibration | null
      return c && Number.isInteger(c.image_width) && Number.isInteger(c.image_height) && Array.isArray(c.corners) && c.corners.length === 4 && c.corners.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1) ? c : null
    } catch { return null }
  })
  const frameSequence = useRef(0)
  const stillRequest = useRef<AbortController | null>(null)
  const previousManual = useRef<Calibration | null>(null)
  useEffect(() => () => { stillRequest.current?.abort() }, [])
  useEffect(() => () => { if (frame?.image.startsWith('blob:')) URL.revokeObjectURL(frame.image) }, [frame])
  const fileInput = useRef<HTMLInputElement>(null)
  const lastDimensions = useRef(dimensions)
  const modal = useRef<HTMLDialogElement>(null)
  const isLive = !!camera.stream
  const balls = result?.balls ?? EMPTY_BALLS
  const activeBall = balls.find(ball => ball.id === selected)

  useEffect(() => { if (settingsOpen) modal.current?.showModal(); else modal.current?.close() }, [settingsOpen])

  // Shot predictions are recomputed only when the (stabilised) ball layout actually changes.
  const ratio = result?.geometry.table_ratio ?? settings.table_ratio
  const ballsKey = useMemo(() => JSON.stringify(balls.map(ball => [ball.id, ball.kind, +ball.x.toFixed(3), +ball.y.toFixed(3), ball.radius])), [balls])
  useEffect(() => {
    setShotPlan(null); setShotError('')
    if (!showShots || !balls.length) { setShotPlan(null); return }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      jsonRequest<ShotsResponse>('/shots', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ balls, table_ratio: ratio, top_n: 5 }), signal: controller.signal })
        .then(plan => { if (!controller.signal.aborted) { setShotPlan(plan); setActiveShot(index => Math.max(0, Math.min(index, plan.shots.length - 1))) } })
        .catch(reason => { if (!controller.signal.aborted) setShotError((reason as Error).message) })
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showShots, ballsKey, ratio])

  // Cue-stick aim: re-run the physics roll-out while the aim point (or layout) moves,
  // then play the resulting ball motion in real time.
  const aimKey = aim ? `${aim.x.toFixed(3)}:${aim.y.toFixed(3)}` : ''
  const cueBall = balls.find(ball => ball.kind === 'cue')
  useEffect(() => {
    setMotion(null); setMotionElapsed(0); setMotionError('')
    if (!aimMode || !aim || !cueBall) { setMotion(null); setMotionElapsed(0); return }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      // Power (0-1) comes from the aiming drag distance, like drawing back the cue.
      const drag = Math.hypot((aim.x - cueBall.x) * ratio, aim.y - cueBall.y)
      jsonRequest<MotionPrediction>('/shots/simulate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ balls, table_ratio: ratio, aim_x: aim.x, aim_y: aim.y, power: Math.min(1, drag / 0.85) }),
      }).then(roll => { if (!controller.signal.aborted) { setMotion(roll); setMotionElapsed(0) } }).catch(reason => { if (!controller.signal.aborted) setMotionError((reason as Error).message) })
    }, 90)
    return () => { clearTimeout(timer); controller.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aimMode, aimKey, ballsKey, ratio])

  // Animate the predicted motion at 1× real time; the final resting layout stays on screen.
  useEffect(() => {
    if (!motion || motion.status !== 'ok' || motion.duration <= 0) { setMotionElapsed(0); return }
    let raf = 0
    const started = performance.now()
    const tick = (now: number) => {
      const t = (now - started) / 1000
      setMotionElapsed(t < motion.duration ? t : motion.duration)
      if (t < motion.duration) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [motion])

  function motionNote(p: MotionPrediction | null): string {
    if (!p) return 'Drag on the table to aim the cue.'
    if (p.status !== 'ok') return SHOT_MESSAGES[p.status] ?? 'Aim the cue from the white ball.'
    if (p.first_ball_id === null) return 'No ball on the aim line · nothing will be pocketed.'
    const contact = p.events.find(event => event.type === 'contact' && event.with === p.cue_ball_id)
    const pots = p.events.filter(event => event.type === 'pot')
    const cushions = p.events.filter(event => event.type === 'cushion').length
    const hit = contact ? `hit at ${contact.t.toFixed(2)} s, cut ${Math.round(contact.cut_angle ?? 0)}°` : 'hit'
    const potted = pots.length
      ? ` · potted: ${pots.map(event => `ball ${event.ball} → ${POCKET_NAMES[event.pocket ?? 0]}`).join(', ')}`
      : ' · nothing potted'
    return `Ball ${p.first_ball_id} ${hit}${potted} · ${cushions} cushion${cushions === 1 ? '' : 's'}`
  }

  function toggleAim() {
    setAimMode(previous => !previous); setAim(null); setMotion(null); setMotionElapsed(0)
  }

  // Sequential sampling, never a queue of stale frames. Camera/settings changes
  // and disconnect abort pending requests and prevent old responses rendering.
  useEffect(() => {
    if (!camera.stream || editing) return
    const identity = session.current
    if (!identity || identity.stream !== camera.stream || identity.unstable !== unstableCamera || identity.manual !== manual || identity.revision !== calibrationRevision) {
      fixedCalibration.current = manual
      consensus.current.reset()
      stabilizer.current.reset()
      session.current = { stream: camera.stream, unstable: unstableCamera, manual, revision: calibrationRevision }
    }
    const controller = new AbortController(), capture = document.createElement('canvas')
    let timer: ReturnType<typeof setTimeout>, active = true, lastCompleted = 0
    setResult(null); setCalibration(fixedCalibration.current); setSelected(null); setStatus(unstableCamera ? 'Looking for the table…' : 'Calibrating the fixed camera. Keep it still…'); setError('')
    const process = async () => {
      const player = camera.video.current
      if (!active || !player) return
      if (player.readyState < 2 || !player.videoWidth) { timer = setTimeout(process, 150); return }
      if (Math.min(player.videoWidth, player.videoHeight) < 100) {
        setResult(null); setError(''); setStatus('Waiting for camera frames. Check that the camera is available and access is allowed.')
        timer = setTimeout(process, 250); return
      }
      const start = performance.now(), scale = Math.min(1, 1280 / player.videoWidth, 960 / player.videoHeight)
      capture.width = Math.round(player.videoWidth * scale); capture.height = Math.round(player.videoHeight * scale)
      const size = { width: capture.width, height: capture.height }
      if (size.width !== lastDimensions.current.width || size.height !== lastDimensions.current.height) {
        lastDimensions.current = size; setDimensions(size)
        if (fixedCalibration.current && (fixedCalibration.current.image_width !== size.width || fixedCalibration.current.image_height !== size.height)) {
          fixedCalibration.current = null; consensus.current.reset(); stabilizer.current.reset()
        }
      }
      capture.getContext('2d')!.drawImage(player, 0, 0, capture.width, capture.height)
      try {
        const blob = await new Promise<Blob>((resolve, reject) => capture.toBlob(value => value ? resolve(value) : reject(new Error('Could not read the camera frame.')), 'image/jpeg', 0.92))
        if (!active) return
        const locked = !unstableCamera ? fixedCalibration.current : null
        const response = await recognize(blob, settings, locked, String(++frameSequence.current), AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]))
        if (!active) return
        setError('')
        if (!response.calibration || !response.detection) {
          setResult(null); stabilizer.current.reset(); consensus.current.reset()
          if (!locked) setCalibration(null)
          setStatus('Looking for the table. Keep all four cloth corners in view.')
        } else if (unstableCamera) {
          setResult(response.detection); setCalibration(response.calibration)
          setStatus('Camera unstable · updating table corners live.')
        } else if (!locked) {
          const candidate = consensus.current.add(response.calibration)
          setCalibration(response.calibration)
          if (candidate) {
            fixedCalibration.current = candidate
            setCalibration(candidate)
            setStatus('Corners locked. Starting steady ball detection…')
          } else setStatus(`Calibrating fixed camera · ${consensus.current.progress} / ${consensus.current.target} consistent frames. Keep the camera still.`)
          // Do not map balls with a single-frame homography then display them
          // against the consensus geometry; the next request uses the lock.
          setResult(null)
        } else {
          setCalibration(locked)
          setResult(stabilizer.current.update(response.detection, jitterTolerance))
          setStatus('Camera fixed · corners locked, ball positions stabilized.')
        }
        const now = performance.now()
        if (lastCompleted) setUpdates(1000 / (now - lastCompleted))
        lastCompleted = now
      } catch (reason) {
        if (!active) return
        setResult(null); stabilizer.current.reset(); consensus.current.reset(); setUpdates(0)
        setError((reason as Error).message); setStatus('Waiting for the detection service…')
      }
      if (active) timer = setTimeout(process, Math.max(100, 500 - (performance.now() - start)))
    }
    void process()
    return () => { active = false; clearTimeout(timer); controller.abort() }
  }, [camera.stream, camera.video, settings, manual, editing, unstableCamera, calibrationRevision, jitterTolerance])

  useEffect(() => {
    if (!camera.stream && !frame) { setResult(null); setCalibration(null); stabilizer.current.reset(); consensus.current.reset(); setUpdates(0); setStatus('Choose a camera to get started.') }
  }, [camera.stream, frame])

  async function connect(id = camera.deviceId) {
    stillRequest.current?.abort()
    setFrame(null); setManual(null); setEditing(false); setResult(null); setError(''); setSelected(null)
    await camera.connect(id)
  }

  async function detectStill(current: Frame, override: Calibration | null = null, options = settings) {
    stillRequest.current?.abort()
    const controller = new AbortController()
    stillRequest.current = controller
    setResult(null); setSelected(null)
    const blob = await (await fetch(current.image, { signal: controller.signal })).blob()
    const detected = await recognize(blob, options, override, String(++frameSequence.current), AbortSignal.any([controller.signal, AbortSignal.timeout(60000)]))
    if (controller.signal.aborted) return false
    setCalibration(detected.calibration); setResult(detected.detection)
    if (!detected.calibration) setStatus('Table not found. Set the corners in settings.')
    return !!detected.calibration
  }

  async function loadImage(blob: Blob, name: string, synthetic = false) {
    const prepared = await localFrame(blob, name, synthetic)
    setFrame(prepared.frame)
    return prepared.frame
  }

  async function sample() {
    camera.stop(); camera.setError(''); setBusy(true); setError(''); setEditing(false); setManual(null); setSelected(null); setResult(null); setCalibration(null)
    try {
      const response = await fetch('/sample-table.png')
      if (!response.ok) throw new Error('Could not load the sample image.')
      const demo = await loadImage(await response.blob(), 'Sample table', true)
      setSettings(DEFAULT_SETTINGS)
      if (await detectStill(demo, null, DEFAULT_SETTINGS)) setStatus('Sample image · live mode starts when you connect a camera.')
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }

  async function upload(file: File) {
    camera.stop(); camera.setError(''); setBusy(true); setError(''); setEditing(false); setManual(null); setResult(null); setCalibration(null); setSelected(null)
    try {
      const current = await loadImage(file, file.name)
      if (await detectStill(current)) setStatus('Still image · connect a camera for live detection.')
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }

  function editCorners() {
    previousManual.current = manual
    const player = camera.video.current
    let current = frame
    if (isLive && player?.videoWidth) {
      const canvas = document.createElement('canvas')
      canvas.width = dimensions.width; canvas.height = dimensions.height
      canvas.getContext('2d')!.drawImage(player, 0, 0, canvas.width, canvas.height)
      current = { image: canvas.toDataURL('image/jpeg', 0.95), ...dimensions, name: 'Calibration frame', synthetic: false }
      setFrame(current)
    }
    if (!current) return
    setManual(calibration ?? { image_width: current.width, image_height: current.height, corners: [] })
    setEditing(true); setSettingsOpen(false); setResult(null)
    setStatus('Place four corners clockwise, starting along a long table edge.')
  }

  async function applyCorners() {
    if (!manual || manual.corners.length !== 4) return
    setUnstableCamera(false)
    setEditing(false)
    if (isLive) setFrame(null)
    else if (frame) {
      setBusy(true)
      try { await detectStill(frame, manual); setStatus('Manual calibration applied.') } catch (reason) { setError((reason as Error).message) }
      finally { setBusy(false) }
    }
  }

  async function recalibrate() {
    setManual(null); fixedCalibration.current = null; consensus.current.reset(); stabilizer.current.reset()
    setResult(null); setCalibration(null); setEditing(false); setSelected(null)
    if (isLive) { setFrame(null); setCalibrationRevision(value => value + 1) }
    else if (frame) {
      setBusy(true); setError('')
      try { if (await detectStill(frame)) setStatus('Corners recalibrated from this image.') }
      catch (reason) { setError((reason as Error).message) }
      finally { setBusy(false) }
    }
  }

  async function useSavedCorners() {
    if (!saved || !canReuse) return
    setUnstableCamera(false); setManual(saved); setResult(null); setSelected(null); setError('')
    if (!isLive && frame) {
      setBusy(true)
      try { await detectStill(frame, saved); setStatus('Saved corners applied.') }
      catch (reason) { setError((reason as Error).message) }
      finally { setBusy(false) }
    } else setStatus('Saved corners applied. Keep the camera in the same position.')
  }

  async function cancelCalibration() {
    setEditing(false); setManual(previousManual.current)
    if (isLive) setFrame(null)
    else if (frame) {
      setBusy(true)
      try { await detectStill(frame, previousManual.current); setStatus('Calibration cancelled.') }
      catch (reason) { setError((reason as Error).message) }
      finally { setBusy(false) }
    }
  }

  const changeSettings = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings(previous => ({ ...previous, [key]: value }))
    stabilizer.current.reset()
    if (!isLive) setResult(null)
  }
  const shownFrame = !isLive || editing ? frame : null
  const shownCalibration = editing ? manual : calibration
  const frameSize = shownFrame ?? dimensions
  const canReuse = saved && saved.image_width === frameSize.width && saved.image_height === frameSize.height

  return <div className="studio">
    <header className="app-header"><a className="brand" href="#"><CircleDot size={25} strokeWidth={1.6} /><span>ball<span className="brand-slash">/</span>detect</span></a><button className="icon-button settings-trigger" onClick={() => setSettingsOpen(true)} aria-label="Open settings"><Settings2 size={20} /></button></header>
    <main className="workspace">
      <section className="intro"><div className="eyebrow">A LIVE VIEW OF YOUR TABLE</div><h1>From table to canvas.</h1><p>Choose your camera. We’ll find the table and map the balls.</p></section>
      <div className="camera-controls"><div className="camera-select"><Camera size={18} /><select aria-label="Choose camera" value={camera.deviceId} disabled={camera.connecting || busy} onChange={event => {
        const id = event.target.value; camera.setDeviceId(id)
        if (isLive) void connect(id)
      }}><option value="">Default camera</option>{camera.devices.filter(device => device.deviceId).map((device, index) => <option value={device.deviceId} key={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}</select><ChevronDown size={15} /></div>
        <button className={isLive || camera.connecting ? 'secondary-button' : 'primary-button'} disabled={busy} onClick={() => {
          if (camera.connecting) camera.stop()
          else if (isLive) { camera.stop(); setEditing(false); setFrame(null); setError('') }
          else void connect()
        }}>{camera.connecting ? <X size={16} /> : isLive ? <Square size={12} fill="currentColor" /> : <Video size={17} />}{camera.connecting ? 'Cancel connection' : isLive ? 'Disconnect' : 'Connect camera'}</button>
      </div>
      <div className="stability-controls"><label className="camera-switch"><input role="switch" type="checkbox" aria-label="Camera is unstable" checked={unstableCamera} disabled={busy || camera.connecting || editing} onChange={event => { setUnstableCamera(event.target.checked); if (isLive) { setManual(null); setResult(null) } }} /><span className="switch-track" /><span>Camera is unstable</span></label><button className="text-button" disabled={!isLive && !frame || busy || camera.connecting} onClick={recalibrate}><RefreshCw size={14} /> Recalibrate corners</button></div>
      {(error || camera.error) && <div className="error-message" role="alert">{camera.error || error}<button className="icon-button" onClick={() => { camera.setError(''); setError('') }} aria-label="Dismiss error"><X size={16} /></button></div>}
      <div className="views">
        <section className="view-panel"><div className="view-heading"><h2>Camera</h2>{isLive && !editing ? <span className="live-badge"><i />LIVE</span> : frame ? <span className="view-caption">{frame.synthetic ? 'SAMPLE IMAGE' : editing ? 'CALIBRATION' : 'STILL IMAGE'}</span> : <span className="view-caption">NOT CONNECTED</span>}</div>
          <div className={`camera-stage ${isLive || frame ? 'has-source' : ''}`}>
            <video ref={camera.video} autoPlay muted playsInline className={isLive && !editing ? '' : 'hidden-video'} aria-label="Live camera feed" />
            {shownFrame && <SourceView frame={shownFrame} corners={shownCalibration?.corners ?? []} editing={editing} onCorners={corners => setManual(previous => previous ? { ...previous, corners } : null)} balls={balls} selected={selected} onSelect={setSelected} showLabels={showIds} />}
            {isLive && !editing && calibration && <svg className="live-overlay" preserveAspectRatio="xMidYMid meet" viewBox={`0 0 ${dimensions.width} ${dimensions.height}`} aria-label="Live table and ball detections">
              <polygon points={calibration.corners.map(p => `${p.x * (dimensions.width - 1)},${p.y * (dimensions.height - 1)}`).join(' ')} fill="none" stroke="#c5efd0" strokeWidth="1.5" strokeDasharray="7 5" vectorEffect="non-scaling-stroke" />
              {balls.map(ball => <circle key={ball.id} cx={ball.source_x * (dimensions.width - 1)} cy={ball.source_y * (dimensions.height - 1)} r={dimensions.width * 0.014} fill="transparent" stroke="#c5efd0" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />)}
            </svg>}
            {!isLive && !frame && <div className="camera-empty"><span className="empty-camera-icon"><Camera size={31} strokeWidth={1.2} /></span><h3>Your camera goes here</h3><p>Keep the whole playing surface in view.</p><button className="text-button" disabled={busy || camera.connecting} onClick={sample}>{busy ? <Loader2 size={14} className="spin" /> : null}Try a sample image</button></div>}
            {busy && (isLive || frame) && <div className="processing-label"><Loader2 className="spin" size={14} /> Detecting…</div>}
          </div>
        </section>
        <section className="view-panel"><div className="view-heading"><h2>Virtual table</h2><span className="view-caption">{result ? `${balls.length} BALL${balls.length === 1 ? '' : 'S'} DETECTED` : 'WAITING FOR A TABLE'}</span></div><div className="virtual-stage"><TableCanvas balls={balls} ratio={ratio} selected={selected} onSelect={setSelected} showLabels={showIds} showGrid={showGrid} shots={shotPlan?.status === 'ok' ? shotPlan.shots : EMPTY_SHOTS} activeShot={activeShot} aimMode={aimMode} aim={aim} motion={motion} motionElapsed={motionElapsed} onAim={point => setAim(point)} /></div>{balls.length > 0 && <div className="aim-row"><button className={`aim-toggle ${aimMode ? 'active' : ''}`} aria-pressed={aimMode} onClick={toggleAim}><Crosshair size={13} /> {aimMode ? 'Aim cue: on' : 'Aim cue'}</button>{aimMode && <span className="shot-note" aria-label="Cue prediction" role="status">{motionError || motionNote(motion)}</span>}</div>}{showShots && shotError && <div className="shot-list"><span className="shot-note" role="alert">{shotError}</span></div>}{showShots && shotPlan && (shotPlan.status === 'ok'
          ? <div className="shot-list" aria-label="Predicted shots">{shotPlan.shots.length === 0 ? <span className="shot-note">No makeable shots found.</span> : shotPlan.shots.map((shot, index) => <button key={`${shot.target_ball_id}-${shot.pocket}-${shot.shot_type}`} className={`shot-chip ${index === activeShot ? 'active' : ''}`} onClick={() => setActiveShot(index)}>{index + 1}. {shot.shot_type === 'bank' ? 'Bank' : 'Direct'} · ball {shot.target_ball_id} → {POCKET_NAMES[shot.pocket]} · {Math.round(shot.score * 100)}%</button>)}</div>
          : <div className="shot-list"><span className="shot-note">{SHOT_MESSAGES[shotPlan.status]}</span></div>)}{balls.length > 0 && <div className="ball-legend" aria-label="Ball types">{(['cue', 'eight', 'solid', 'striped', 'unknown'] as const).filter(kind => kind !== 'unknown' || balls.some(ball => ball.kind === kind)).map(kind => <span key={kind}><i className={`mini-ball ${kind}`} style={{ '--ball-color': BALL_COLORS[kind] } as React.CSSProperties} />{BALL_NAMES[kind]}</span>)}</div>}</section>
      </div>
      <div className="status-line" role="status"><span className={`status-dot ${isLive && result ? 'live' : ''}`} />{busy ? 'Finding the table and balls…' : camera.connecting ? 'Opening camera…' : status}{isLive && result && updates > 0 && <span className="update-rate">{updates.toFixed(1)} updates / sec</span>}</div>
      {editing && <div className="calibration-strip"><span>{manual?.corners.length ?? 0} / 4 corners · drag to adjust</span><button className="text-button" onClick={() => setManual(previous => previous ? { ...previous, corners: [] } : null)}>Reset corners</button><button className="text-button" disabled={manual?.corners.length !== 4} onClick={() => setManual(previous => previous ? { ...previous, corners: [...previous.corners.slice(1), previous.corners[0]] } : null)}>Rotate mapping</button><button className="primary-button" disabled={manual?.corners.length !== 4} onClick={applyCorners}><Check size={15} /> Use these corners</button><button className="icon-button" aria-label="Cancel calibration" onClick={cancelCalibration}><X size={17} /></button></div>}
      {activeBall && <div className="ball-inspector"><span className={`mini-ball ${activeBall.kind}`} style={{ '--ball-color': BALL_COLORS[activeBall.kind] } as React.CSSProperties} /><strong>{BALL_NAMES[activeBall.kind]}</strong><span>x {activeBall.x.toFixed(3)} <span className="inspector-separator">/</span> y {activeBall.y.toFixed(3)}</span><span className="ball-reason">{activeBall.reason}</span><button className="icon-button" onClick={() => setSelected(null)} aria-label="Close ball details"><X size={15} /></button></div>}
      <footer><span>All image processing runs on your detection server.</span><span>Best results with a fixed camera and steady light.</span></footer>
    </main>

    <dialog ref={modal} className="settings-dialog" onCancel={() => setSettingsOpen(false)} onClick={event => { if (event.target === modal.current) setSettingsOpen(false) }} aria-labelledby="settings-title"><div className="settings-content"><div className="settings-heading"><h2 id="settings-title">Settings</h2><button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="Close settings" autoFocus><X size={20} /></button></div>
      <fieldset className="settings-fields" disabled={busy}><section className="settings-section"><h3>Camera & calibration</h3><p>With a fixed camera, eight consistent frames calibrate and lock the corners. Enable “Camera is unstable” to update them every frame. Recalibrate after moving a fixed camera.</p><div className="settings-button-row"><button className="secondary-button" onClick={camera.refresh}><RefreshCw size={14} /> Refresh cameras</button><button className="secondary-button" disabled={!isLive && !frame || busy} onClick={editCorners}><Crosshair size={14} /> Set corners manually</button></div>
      {manual && <button className="text-button auto-button" onClick={recalibrate}>Return to automatic calibration</button>}
      <div className="settings-button-row"><button className="text-button" disabled={!calibration} onClick={() => { if (!calibration) return; try { localStorage.setItem('live-table-calibration', JSON.stringify(calibration)); setSaved(calibration); setStatus('Corners saved for this camera position and resolution.') } catch { setError('Could not save calibration in this browser.') } }}>Save current corners</button><button className="text-button" disabled={!canReuse || !frame && !isLive} onClick={useSavedCorners}>Use saved corners</button></div>
      </section>
      <TableSetup settings={settings} onChange={next => {
        setSettings(next); stabilizer.current.reset()
        if (!isLive) setResult(null)
      }} />
      <section className="settings-section"><h3>Detection</h3><label className="range-label"><span>Table proportions <strong>{settings.table_ratio.toFixed(2)} : 1</strong></span><input type="range" min="1" max="3" step="0.05" value={settings.table_ratio} onChange={event => changeSettings('table_ratio', Number(event.target.value))} /></label><label className="range-label"><span>Ball radius / table height <strong>{(settings.ball_radius_ratio * 100).toFixed(1)}%</strong></span><input type="range" min="0.012" max="0.06" step="0.001" value={settings.ball_radius_ratio} onChange={event => changeSettings('ball_radius_ratio', Number(event.target.value))} /></label><label className="range-label"><span>Cloth hue tolerance <strong>±{settings.hue_tolerance}</strong></span><input type="range" min="3" max="40" value={settings.hue_tolerance} onChange={event => changeSettings('hue_tolerance', Number(event.target.value))} /></label><label className="range-label"><span>Stationary-ball tolerance <strong>{(jitterTolerance * 100).toFixed(1)}% of table height</strong></span><input type="range" min="0.002" max="0.015" step="0.001" value={jitterTolerance} onChange={event => setJitterTolerance(Number(event.target.value))} /></label><label className="checkbox-label"><input type="checkbox" checked={settings.split_touching} onChange={event => changeSettings('split_touching', event.target.checked)} /> Separate touching balls</label><label className="checkbox-label"><input type="checkbox" checked={showIds} onChange={event => setShowIds(event.target.checked)} /> Show ball IDs</label><label className="checkbox-label"><input type="checkbox" checked={showGrid} onChange={event => setShowGrid(event.target.checked)} /> Show table grid</label><label className="checkbox-label"><input type="checkbox" checked={showShots} onChange={event => setShowShots(event.target.checked)} /> Show shot predictions</label>
      {frame && !isLive && <button className="secondary-button" disabled={busy || editing} onClick={async () => { setBusy(true); setError(''); try { await detectStill(frame, manual) } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) } }}>Apply to image</button>}
      </section>
      <section className="settings-section"><h3>Test & export</h3><div className="settings-button-row"><button className="secondary-button" disabled={busy || camera.connecting} onClick={() => { setSettingsOpen(false); void sample() }}><ImagePlus size={14} /> Try sample</button><button className="secondary-button" disabled={busy || camera.connecting} onClick={() => fileInput.current?.click()}><ImagePlus size={14} /> Upload photo</button><button className="secondary-button" disabled={!result} onClick={() => result && downloadJSON({ ...result, display_stabilized: isLive && !unstableCamera, calibration, settings, synthetic: frame?.synthetic ?? false, captured_at: new Date().toISOString() }, 'table-layout.json')}><ArrowDownToLine size={14} /> Export layout</button></div><p className="limitations">Balls are shown as white, black, full, half, or unknown. Individual colors are ignored. Hidden stripes and occlusion can be ambiguous. Coordinates use the cloth plane, so angled cameras introduce parallax. Fixed-camera mode suppresses small position changes and brief detection dropouts. Session labels are approximate associations, not guaranteed ball identities.</p></section>
    </fieldset></div></dialog>
    <input ref={fileInput} hidden type="file" accept="image/jpeg,image/png,image/webp" aria-label="Upload table photo" onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) { setSettingsOpen(false); void upload(file) } }} />
  </div>
}
