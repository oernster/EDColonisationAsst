/**
 * Characterisation tests for the three keep-awake strategy modules.
 *
 * useKeepAwake.ts was one 406-line file with no tests at all. Its length was
 * the sequence of strategies it fell through rather than layout, so it came
 * apart by strategy: the capability probes, the fallback video and the
 * compositor heartbeat. What these assert is that each of those behaves as it
 * did inside the hook.
 *
 * jsdom implements none of what this code reaches for, so navigator.wakeLock,
 * UA-CH, touch, canvas capture streams and media playback are all hand-written
 * fakes patched on for the duration of a test and taken off afterwards.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import {
  canUseWakeLock,
  isMobileOrTabletLike,
  isSecureContextForWakeLock,
} from './keepAwakeCapabilities'
import { createHiddenVideoElement, destroyHiddenVideoElement } from './keepAwakeVideo'
import { useRepaintHeartbeat } from './useRepaintHeartbeat'

type Patch = { target: object; key: string; had: boolean; previous: unknown }

const patches: Patch[] = []

/** Define a property the environment does not have, remembering what was there. */
const patch = (target: object, key: string, value: unknown) => {
  patches.push({
    target,
    key,
    had: key in target,
    previous: (target as Record<string, unknown>)[key],
  })
  Object.defineProperty(target, key, { configurable: true, writable: true, value })
}

/** Take a property away that the environment does have, for the same duration. */
const unpatch = (target: object, key: string) => {
  patches.push({
    target,
    key,
    had: key in target,
    previous: (target as Record<string, unknown>)[key],
  })
  delete (target as Record<string, unknown>)[key]
}

const restoreAll = () => {
  for (const { target, key, had, previous } of patches.reverse()) {
    if (had) {
      Object.defineProperty(target, key, {
        configurable: true,
        writable: true,
        value: previous,
      })
    } else {
      delete (target as Record<string, unknown>)[key]
    }
  }
  patches.length = 0
}

afterEach(() => {
  restoreAll()
  vi.useRealTimers()
  vi.restoreAllMocks()
  document.body.style.transform = ''
})

/** A capture stream carrying one track, standing in for the real MediaStream. */
const fakeStream = () => {
  const track = { stop: vi.fn() }
  return { stream: { getTracks: () => [track] } as unknown as MediaStream, track }
}

/**
 * jsdom reports a screen of 0x0, which the probe reads as "no screen info" and
 * refuses to call handheld. Give it real dimensions before asking.
 */
const screenOf = (width: number, height: number) => {
  patch(window.screen, 'width', width)
  patch(window.screen, 'height', height)
}

/**
 * jsdom implements no srcObject; the video path checks for it before using a
 * capture stream, so the property has to exist for that branch to be reached.
 */
const allowSrcObject = () => {
  patch(HTMLMediaElement.prototype, 'srcObject', null)
}

/**
 * jsdom carries an `ontouchstart` handler slot on window, which the probe reads
 * as a touch screen, so a no-touch environment has to be made by taking it off.
 * jsdom has no matchMedia at all, which the probe already treats as no coarse
 * pointer.
 */
const withoutTouch = () => {
  unpatch(window, 'ontouchstart')
  patch(navigator, 'maxTouchPoints', 0)
}

describe('keep-awake capability probes', () => {
  it('reports no Wake Lock when the navigator has none', () => {
    expect(canUseWakeLock()).toBe(false)
  })

  it('reports a Wake Lock when request is callable', () => {
    patch(navigator, 'wakeLock', { request: () => Promise.resolve({}) })
    expect(canUseWakeLock()).toBe(true)
  })

  it('reports no Wake Lock when the object is there but request is not callable', () => {
    patch(navigator, 'wakeLock', { request: 'not a function' })
    expect(canUseWakeLock()).toBe(false)
  })

  it('mirrors the secure-context flag', () => {
    patch(window, 'isSecureContext', true)
    expect(isSecureContextForWakeLock()).toBe(true)
    patch(window, 'isSecureContext', false)
    expect(isSecureContextForWakeLock()).toBe(false)
  })

  it('trusts the UA-CH mobile flag over everything else', () => {
    patch(navigator, 'userAgentData', { mobile: true })
    expect(isMobileOrTabletLike()).toBe(true)

    patch(navigator, 'userAgentData', { mobile: false })
    patch(navigator, 'maxTouchPoints', 5)
    expect(isMobileOrTabletLike()).toBe(false)
  })

  it('treats a touch screen of handheld size as handheld', () => {
    screenOf(800, 1280)
    withoutTouch()
    patch(navigator, 'maxTouchPoints', 5)
    expect(isMobileOrTabletLike()).toBe(true)
  })

  it('treats a coarse pointer of handheld size as handheld', () => {
    screenOf(800, 1280)
    withoutTouch()
    patch(window, 'matchMedia', () => ({ matches: true }))
    expect(isMobileOrTabletLike()).toBe(true)
  })

  it('does not treat a touch screen the size of a monitor as handheld', () => {
    screenOf(3840, 2160)
    patch(navigator, 'maxTouchPoints', 5)
    expect(isMobileOrTabletLike()).toBe(false)
  })

  it('does not treat a handheld-sized screen without touch as handheld', () => {
    screenOf(800, 1280)
    withoutTouch()
    expect(isMobileOrTabletLike()).toBe(false)
  })

  it('ignores a fine pointer of handheld size', () => {
    screenOf(800, 1280)
    withoutTouch()
    patch(window, 'matchMedia', () => ({ matches: false }))
    expect(isMobileOrTabletLike()).toBe(false)
  })

  it('does not guess when there is no screen to read', () => {
    screenOf(0, 0)
    patch(navigator, 'maxTouchPoints', 5)
    expect(isMobileOrTabletLike()).toBe(false)
  })
})

describe('keep-awake fallback video', () => {
  it('falls back to the inline data URL where there is no capture stream', () => {
    const video = createHiddenVideoElement()

    expect(video.src.startsWith('data:video/mp4;base64,')).toBe(true)
    expect(video.muted).toBe(true)
    expect(video.loop).toBe(true)
    expect(video.getAttribute('playsinline')).toBe('true')
    expect(video.style.position).toBe('fixed')
    expect(video.style.opacity).toBe('0')
  })

  it('prefers a canvas capture stream and keeps it producing frames', () => {
    vi.useFakeTimers()
    allowSrcObject()
    const { stream } = fakeStream()
    const ctx = { fillStyle: '', fillRect: vi.fn() }
    patch(HTMLCanvasElement.prototype, 'captureStream', () => stream)
    patch(HTMLCanvasElement.prototype, 'getContext', () => ctx)

    const video = createHiddenVideoElement()

    expect(video.src).toBe('')
    expect((video as unknown as { srcObject: MediaStream }).srcObject).toBe(stream)

    vi.advanceTimersByTime(1000)
    expect(ctx.fillRect).toHaveBeenCalledTimes(1)
    const firstFill = ctx.fillStyle
    vi.advanceTimersByTime(1000)
    expect(ctx.fillStyle).not.toBe(firstFill)

    destroyHiddenVideoElement(video)
  })

  it('falls back to the data URL when capturing the canvas throws', () => {
    patch(HTMLCanvasElement.prototype, 'captureStream', () => {
      throw new Error('capture refused')
    })

    expect(createHiddenVideoElement().src.startsWith('data:video/mp4;')).toBe(true)
  })

  it('takes the capture stream down with the element', () => {
    vi.useFakeTimers()
    allowSrcObject()
    const { stream, track } = fakeStream()
    patch(HTMLCanvasElement.prototype, 'captureStream', () => stream)
    patch(HTMLCanvasElement.prototype, 'getContext', () => null)

    const video = createHiddenVideoElement()
    document.body.appendChild(video)

    destroyHiddenVideoElement(video)

    expect(track.stop).toHaveBeenCalledTimes(1)
    expect((video as unknown as { srcObject: MediaStream | null }).srcObject).toBeNull()
    expect((video as unknown as { _edcaKeepAwake?: unknown })._edcaKeepAwake).toBeUndefined()
    expect(document.body.contains(video)).toBe(false)
  })

  it('removes an element that never had a capture stream', () => {
    const video = createHiddenVideoElement()
    document.body.appendChild(video)

    destroyHiddenVideoElement(video)

    expect(document.body.contains(video)).toBe(false)
  })
})

describe('keep-awake compositor heartbeat', () => {
  it('stays off on a desktop', () => {
    vi.useFakeTimers()
    patch(navigator, 'userAgentData', { mobile: false })
    const { result } = renderHook(() => useRepaintHeartbeat())

    act(() => result.current.start())
    vi.advanceTimersByTime(10000)

    expect(document.body.style.transform).toBe('')
  })

  it('nudges the body while running and clears the nudge when stopped', () => {
    vi.useFakeTimers()
    patch(navigator, 'userAgentData', { mobile: true })
    const { result } = renderHook(() => useRepaintHeartbeat())

    act(() => result.current.start())
    vi.advanceTimersByTime(2000)
    expect(document.body.style.transform).toMatch(/^translateZ\(/)

    act(() => result.current.stop())
    expect(document.body.style.transform).toBe('')

    vi.advanceTimersByTime(10000)
    expect(document.body.style.transform).toBe('')
  })

  it('runs one interval however many times it is started', () => {
    vi.useFakeTimers()
    patch(navigator, 'userAgentData', { mobile: true })
    const setInterval = vi.spyOn(window, 'setInterval')
    const { result } = renderHook(() => useRepaintHeartbeat())

    act(() => {
      result.current.start()
      result.current.start()
      result.current.start()
    })

    expect(setInterval).toHaveBeenCalledTimes(1)

    act(() => result.current.stop())
    act(() => result.current.stop())
    expect(document.body.style.transform).toBe('')
  })
})
