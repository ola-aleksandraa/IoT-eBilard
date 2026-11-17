import { useCallback, useEffect, useRef, useState } from 'react'

export function useCamera() {
  const video = useRef<HTMLVideoElement>(null)
  const activeStream = useRef<MediaStream | null>(null)
  const generation = useRef(0)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [deviceId, setDeviceId] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try { setDevices((await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput')) }
    catch { setError('Camera list unavailable. Check browser permissions.') }
  }, [])

  const stop = useCallback(() => {
    generation.current++
    activeStream.current?.getTracks().forEach(track => track.stop())
    activeStream.current = null
    setStream(null); setConnecting(false)
  }, [])

  const connect = useCallback(async (id: string) => {
    stop(); setError(''); setConnecting(true)
    const attempt = generation.current
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Camera access needs localhost or HTTPS.'); setConnecting(false); return
    }
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { ...(id ? { deviceId: { exact: id } } : {}), width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 24, max: 30 } },
        audio: false,
      })
      if (attempt !== generation.current) { media.getTracks().forEach(track => track.stop()); return }
      activeStream.current = media; setStream(media)
      const track = media.getVideoTracks()[0]
      setDeviceId(track.getSettings().deviceId ?? id)
      track.addEventListener('ended', () => {
        if (activeStream.current !== media) return
        stop(); setError('Camera disconnected. Choose a camera and reconnect.'); void refresh()
      }, { once: true })
      await refresh()
    } catch (reason) {
      if (attempt !== generation.current) return
      const name = reason instanceof DOMException ? reason.name : ''
      setError(name === 'NotAllowedError' ? 'Camera permission was denied. Allow camera access in your browser and try again.' : name === 'NotFoundError' || name === 'OverconstrainedError' ? 'This camera is unavailable. Choose another camera.' : 'Could not open this camera. It may be in use by another app.')
    } finally { if (attempt === generation.current) setConnecting(false) }
  }, [refresh, stop])

  useEffect(() => {
    void refresh()
    navigator.mediaDevices?.addEventListener('devicechange', refresh)
    return () => { navigator.mediaDevices?.removeEventListener('devicechange', refresh); generation.current++; activeStream.current?.getTracks().forEach(track => track.stop()) }
  }, [refresh])

  useEffect(() => {
    const player = video.current
    if (!player) return
    player.srcObject = stream
    if (stream) void player.play().catch(() => { if (activeStream.current === stream) { setError('Could not play the camera feed. Reconnect the camera.'); stop() } })
    return () => { player.srcObject = null }
  }, [stream, stop])

  return { video, stream, devices, deviceId, setDeviceId, connecting, error, setError, connect, stop, refresh }
}
