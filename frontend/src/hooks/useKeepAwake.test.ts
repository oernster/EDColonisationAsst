/**
 * Characterisation tests for the keep-awake hook.
 *
 * What is left in useKeepAwake.ts after the strategy modules came out is the
 * order the strategies are tried in and the status that order produces, so
 * that is what these assert: Wake Lock first where it is possible, the hidden
 * video where it is not or where it failed, a tap-to-enable state when the
 * browser blocks autoplay and release on the way out.
 *
 * jsdom has no Wake Lock API and no media playback, so both are hand-written
 * fakes. src/test/setup.ts already makes play() reject, which is autoplay
 * being blocked; the tests that need it to succeed say so.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import { useKeepAwake } from './useKeepAwake'

type Patch = { target: object; key: string; had: boolean; previous: unknown }

const patches: Patch[] = []

const patch = (target: object, key: string, value: unknown) => {
  patches.push({
    target,
    key,
    had: key in target,
    previous: (target as Record<string, unknown>)[key],
  })
  Object.defineProperty(target, key, { configurable: true, writable: true, value })
}

afterEach(() => {
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
  document.body.querySelectorAll('video').forEach((video) => video.remove())
  vi.restoreAllMocks()
})

/** A Wake Lock sentinel that records its listeners so a test can fire one. */
const wakeLockSentinel = () => {
  const listeners: Array<() => void> = []
  const state = { released: false }

  return {
    sentinel: {
      get released() {
        return state.released
      },
      release: vi.fn(() => {
        state.released = true
        return Promise.resolve()
      }),
      addEventListener: vi.fn((_type: string, listener: () => void) => {
        listeners.push(listener)
      }),
      removeEventListener: vi.fn((_type: string, listener: () => void) => {
        const index = listeners.indexOf(listener)
        if (index >= 0) listeners.splice(index, 1)
      }),
    },
    fireRelease: () => listeners.forEach((listener) => listener()),
    listenerCount: () => listeners.length,
  }
}

/** Put a working Wake Lock API in front of the hook and return its parts. */
const grantWakeLock = () => {
  const held = wakeLockSentinel()
  const request = vi.fn(() => Promise.resolve(held.sentinel))
  patch(window, 'isSecureContext', true)
  patch(navigator, 'wakeLock', { request })
  return { ...held, request }
}

const refuseWakeLock = () => {
  const request = vi.fn(() => Promise.reject(new Error('denied')))
  patch(window, 'isSecureContext', true)
  patch(navigator, 'wakeLock', { request })
  return request
}

const allowAutoplay = () => {
  patch(HTMLMediaElement.prototype, 'play', () => Promise.resolve())
}

const render = (enabled: boolean, allowFallbackVideo: boolean) =>
  renderHook(() => useKeepAwake({ enabled, allowFallbackVideo }))

describe('useKeepAwake', () => {
  it('stays off while disabled', async () => {
    const { result } = render(false, true)

    await waitFor(() => expect(result.current.status).toEqual({ state: 'off', message: 'Off' }))
    expect(result.current.wakeLockPossible).toBe(false)
    expect(result.current.secureContext).toBe(false)
  })

  it('reports no Wake Lock outside a secure context even where the API exists', async () => {
    patch(navigator, 'wakeLock', { request: vi.fn() })
    patch(window, 'isSecureContext', false)

    const { result } = render(true, false)

    await waitFor(() => expect(result.current.wakeLockPossible).toBe(false))
  })

  it('takes a Wake Lock when one is possible', async () => {
    const { request, listenerCount } = grantWakeLock()

    const { result } = render(true, true)

    await waitFor(() =>
      expect(result.current.status).toEqual({
        state: 'active',
        mode: 'wake-lock',
        message: 'Keep-awake active (Wake Lock)',
      }),
    )
    expect(request).toHaveBeenCalledWith('screen')
    expect(result.current.wakeLockPossible).toBe(true)
    expect(result.current.secureContext).toBe(true)
    expect(listenerCount()).toBe(1)
    expect(document.body.querySelectorAll('video')).toHaveLength(0)
  })

  it('reports an error when the system takes the Wake Lock back', async () => {
    const { fireRelease } = grantWakeLock()
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('active'))

    act(() => fireRelease())

    expect(result.current.status).toEqual({
      state: 'error',
      message: 'Wake Lock was released by the system',
    })
  })

  it('falls through to the video when the Wake Lock request is refused', async () => {
    const request = refuseWakeLock()

    const { result } = render(true, true)

    await waitFor(() =>
      expect(result.current.status).toEqual({
        state: 'needs-user-gesture',
        message: 'Tap once to enable keep-awake',
      }),
    )
    expect(request).toHaveBeenCalledTimes(1)
    expect(document.body.querySelectorAll('video')).toHaveLength(1)
  })

  it('plays the hidden video where there is no Wake Lock', async () => {
    allowAutoplay()

    const { result } = render(true, true)

    await waitFor(() =>
      expect(result.current.status).toEqual({
        state: 'active',
        mode: 'fallback-video',
        message: 'Keep-awake active (Fallback)',
      }),
    )
    expect(document.body.querySelectorAll('video')).toHaveLength(1)
  })

  it('reports itself unsupported when the fallback is not allowed', async () => {
    const { result } = render(true, false)

    await waitFor(() =>
      expect(result.current.status).toEqual({
        state: 'unsupported',
        message: 'Keep-awake fallback disabled',
      }),
    )
    expect(document.body.querySelectorAll('video')).toHaveLength(0)
  })

  it('asks for a tap when autoplay is blocked, then starts on the next one', async () => {
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('needs-user-gesture'))

    allowAutoplay()
    await act(async () => {
      document.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    await waitFor(() =>
      expect(result.current.status).toEqual({
        state: 'active',
        mode: 'fallback-video',
        message: 'Keep-awake active (Fallback)',
      }),
    )
  })

  it('does not arm the tap listener while the fallback is not allowed', async () => {
    const addEventListener = vi.spyOn(document, 'addEventListener')

    const { result } = render(true, false)
    await waitFor(() => expect(result.current.status.state).toBe('unsupported'))

    expect(addEventListener.mock.calls.map(([type]) => type)).not.toContain('touchstart')
  })

  it('releases everything on stopAll', async () => {
    const { sentinel } = grantWakeLock()
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('active'))

    await act(async () => {
      await result.current.stopAll()
    })

    expect(result.current.status).toEqual({ state: 'off', message: 'Off' })
    expect(sentinel.release).toHaveBeenCalledTimes(1)
    expect(sentinel.removeEventListener).toHaveBeenCalledTimes(1)
    expect(document.body.querySelectorAll('video')).toHaveLength(0)
  })

  it('gives the Wake Lock back while the page is hidden and takes it again on return', async () => {
    const { sentinel, request } = grantWakeLock()
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('active'))

    patch(document, 'visibilityState', 'hidden')
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(sentinel.release).toHaveBeenCalledTimes(1)

    patch(document, 'visibilityState', 'visible')
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    expect(result.current.status.state).toBe('active')
  })

  it('enables from a user gesture without awaiting first', async () => {
    grantWakeLock()
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('active'))

    let enabled: boolean | undefined
    await act(async () => {
      enabled = await result.current.enableFromUserGesture()
    })

    expect(enabled).toBe(true)
  })

  it('refuses to enable from a gesture while disabled', async () => {
    const { result } = render(false, true)
    await waitFor(() => expect(result.current.status.state).toBe('off'))

    let enabled: boolean | undefined
    await act(async () => {
      enabled = await result.current.enableFromUserGesture()
    })

    expect(enabled).toBe(false)
  })

  it('enables from a gesture through the video where there is no Wake Lock', async () => {
    allowAutoplay()
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('active'))

    let enabled: boolean | undefined
    await act(async () => {
      enabled = await result.current.enableFromUserGesture()
    })

    expect(enabled).toBe(true)
    expect(document.body.querySelectorAll('video')).toHaveLength(1)
  })

  it('falls through to the video from a gesture when the Wake Lock is refused', async () => {
    refuseWakeLock()
    allowAutoplay()
    const { result } = render(true, true)
    await waitFor(() => expect(result.current.status.state).toBe('active'))

    let enabled: boolean | undefined
    await act(async () => {
      enabled = await result.current.enableFromUserGesture()
    })

    expect(enabled).toBe(true)
    expect(result.current.status.state).toBe('active')
  })
})
