// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCamera } from './useCamera'

const getUserMedia = vi.fn(), enumerateDevices = vi.fn()

function media(id: string) {
  const events: Record<string, () => void> = {}
  const track = { stop: vi.fn(), getSettings: () => ({ deviceId: id }), addEventListener: (event: string, callback: () => void) => { events[event] = callback } }
  return { stream: { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream, track, events }
}

beforeEach(() => {
  getUserMedia.mockReset(); enumerateDevices.mockReset()
  enumerateDevices.mockResolvedValue([{ kind: 'videoinput', deviceId: 'usb', label: 'USB camera' }, { kind: 'audioinput', deviceId: 'mic' }])
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia, enumerateDevices, addEventListener: vi.fn(), removeEventListener: vi.fn() } })
})
afterEach(cleanup)

describe('camera lifecycle', () => {
  it('lists video devices and requests the selected camera without audio', async () => {
    const usb = media('usb'); getUserMedia.mockResolvedValue(usb.stream)
    const { result } = renderHook(useCamera)
    await act(async () => { await result.current.connect('usb') })
    expect(getUserMedia).toHaveBeenCalledWith({ video: { deviceId: { exact: 'usb' }, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 24, max: 30 } }, audio: false })
    expect(result.current.devices).toHaveLength(1)
    expect(result.current.deviceId).toBe('usb')
    expect(result.current.stream).toBe(usb.stream)
  })

  it('stops the old stream when switching cameras and releases on unmount', async () => {
    const first = media('first'), second = media('second')
    getUserMedia.mockResolvedValueOnce(first.stream).mockResolvedValueOnce(second.stream)
    const { result, unmount } = renderHook(useCamera)
    await act(async () => { await result.current.connect('first') })
    await act(async () => { await result.current.connect('second') })
    expect(first.track.stop).toHaveBeenCalledOnce()
    expect(result.current.deviceId).toBe('second')
    unmount(); expect(second.track.stop).toHaveBeenCalledOnce()
  })

  it('does not resurrect a camera when an in-flight permission request completes after stop', async () => {
    const usb = media('usb')
    let resolve!: (stream: MediaStream) => void
    getUserMedia.mockReturnValue(new Promise<MediaStream>(r => { resolve = r }))
    const { result } = renderHook(useCamera)
    let connection!: Promise<void>
    act(() => { connection = result.current.connect('usb') })
    act(() => result.current.stop())
    await act(async () => { resolve(usb.stream); await connection })
    expect(result.current.stream).toBeNull()
    expect(usb.track.stop).toHaveBeenCalledOnce()
  })

  it('clears live state when a camera is unplugged', async () => {
    const usb = media('usb'); getUserMedia.mockResolvedValue(usb.stream)
    const { result } = renderHook(useCamera)
    await act(async () => { await result.current.connect('usb') })
    await act(async () => { usb.events.ended() })
    expect(result.current.stream).toBeNull()
    expect(result.current.error).toContain('disconnected')
  })

  it('reports permission denial without leaving a connecting state', async () => {
    getUserMedia.mockRejectedValue(new DOMException('denied', 'NotAllowedError'))
    const { result } = renderHook(useCamera)
    await act(async () => { await result.current.connect('usb') })
    expect(result.current.error).toContain('permission was denied')
    expect(result.current.connecting).toBe(false)
    expect(result.current.stream).toBeNull()
  })
})
