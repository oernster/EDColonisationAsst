import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  WakeLockSentinelLike,
  canUseWakeLock,
  getWakeLock,
  isSecureContextForWakeLock,
} from './keepAwakeCapabilities';
import { createHiddenVideoElement, destroyHiddenVideoElement } from './keepAwakeVideo';
import { useRepaintHeartbeat } from './useRepaintHeartbeat';

export type KeepAwakeMode = 'wake-lock' | 'fallback-video' | 'off';

export type KeepAwakeStatus =
  | { state: 'off'; message: string }
  | { state: 'active'; mode: KeepAwakeMode; message: string }
  | { state: 'needs-user-gesture'; message: string }
  | { state: 'unsupported'; message: string }
  | { state: 'error'; message: string };

type Options = {
  enabled: boolean;
  // When Wake Lock isn't available (e.g. HTTP LAN URL), we can fall back to a
  // hidden looping video. Autoplay restrictions mean it needs a user gesture.
  allowFallbackVideo: boolean;
};

/**
 * Keeps the screen awake, preferring the Wake Lock API and falling back to a
 * hidden video where there is none. The capability probes, the fallback video
 * and the compositor heartbeat each live in their own module; what is left
 * here is the order the strategies are tried in and the status that order
 * produces.
 */
export const useKeepAwake = ({ enabled, allowFallbackVideo }: Options) => {
  const [status, setStatus] = useState<KeepAwakeStatus>({ state: 'off', message: 'Off' });

  const sentinelRef = useRef<WakeLockSentinelLike | null>(null);
  const sentinelReleaseListenerRef = useRef<(() => void) | null>(null);

  const fallbackVideoRef = useRef<HTMLVideoElement | null>(null);
  const gestureListenerBoundRef = useRef(false);

  const { start: startRepaintHeartbeat, stop: stopRepaintHeartbeat } = useRepaintHeartbeat();

  const wakeLockPossible = useMemo(() => {
    return canUseWakeLock() && isSecureContextForWakeLock();
  }, []);

  const releaseWakeLock = useCallback(async () => {
    try {
      // Remove any release listener we attached.
      if (sentinelRef.current && sentinelReleaseListenerRef.current) {
        try {
          sentinelRef.current.removeEventListener?.('release', sentinelReleaseListenerRef.current);
        } catch {
          // ignore
        }
      }
      sentinelReleaseListenerRef.current = null;

      if (sentinelRef.current && !sentinelRef.current.released) {
        await sentinelRef.current.release();
      }
    } catch {
      // Best-effort.
    } finally {
      sentinelRef.current = null;
      stopRepaintHeartbeat();
    }
  }, [stopRepaintHeartbeat]);

  const stopFallbackVideo = useCallback(() => {
    const video = fallbackVideoRef.current;
    if (!video) return;

    destroyHiddenVideoElement(video);
    fallbackVideoRef.current = null;
  }, []);

  const stopAll = useCallback(async () => {
    await releaseWakeLock();
    stopFallbackVideo();
    stopRepaintHeartbeat();
    setStatus({ state: 'off', message: 'Off' });
  }, [releaseWakeLock, stopFallbackVideo, stopRepaintHeartbeat]);

  const requestWakeLock = useCallback(async () => {
    const wakeLock = getWakeLock();
    if (!wakeLock) {
      setStatus({ state: 'unsupported', message: 'Wake Lock API not available' });
      return false;
    }
    if (!isSecureContextForWakeLock()) {
      setStatus({ state: 'unsupported', message: 'Wake Lock requires HTTPS/localhost' });
      return false;
    }

    try {
      const sentinel = await wakeLock.request('screen');
      sentinelRef.current = sentinel;

      // If the OS releases the lock, reflect that and allow re-acquire on visibility changes.
      const onRelease = () => {
        // Only update if we still consider keep-awake enabled.
        setStatus({ state: 'error', message: 'Wake Lock was released by the system' });
        stopRepaintHeartbeat();
      };
      sentinelReleaseListenerRef.current = onRelease;
      sentinel.addEventListener?.('release', onRelease);

      setStatus({ state: 'active', mode: 'wake-lock', message: 'Keep-awake active (Wake Lock)' });

      // Heartbeat while Wake Lock is active.
      startRepaintHeartbeat();

      return true;
    } catch {
      setStatus({ state: 'error', message: 'Failed to acquire Wake Lock' });
      return false;
    }
  }, [startRepaintHeartbeat, stopRepaintHeartbeat]);

  const startFallbackVideo = useCallback(async () => {
    if (!allowFallbackVideo) {
      setStatus({ state: 'unsupported', message: 'Keep-awake fallback disabled' });
      return false;
    }

    if (!fallbackVideoRef.current) {
      fallbackVideoRef.current = createHiddenVideoElement();
      document.body.appendChild(fallbackVideoRef.current);
    }
    const video = fallbackVideoRef.current;

    try {
      await video.play();
      setStatus({ state: 'active', mode: 'fallback-video', message: 'Keep-awake active (Fallback)' });
      // Fallback already produces frames; heartbeat unnecessary.
      stopRepaintHeartbeat();
      return true;
    } catch {
      setStatus({ state: 'needs-user-gesture', message: 'Tap once to enable keep-awake' });
      stopRepaintHeartbeat();
      return false;
    }
  }, [allowFallbackVideo, stopRepaintHeartbeat]);

  const ensureEnabled = useCallback(async () => {
    if (!enabled) {
      await stopAll();
      return;
    }

    // Prefer Wake Lock when possible.
    if (wakeLockPossible) {
      const ok = await requestWakeLock();
      if (ok) {
        stopFallbackVideo();
        return;
      }
    }

    // Otherwise, fall back.
    await releaseWakeLock();
    await startFallbackVideo();
  }, [enabled, wakeLockPossible, requestWakeLock, startFallbackVideo, releaseWakeLock, stopAll, stopFallbackVideo]);

  // Attempt to enable within a user-gesture call stack.
  // Avoid "await" before trying to play media, as it can lose the gesture.
  const enableFromUserGesture = useCallback(() => {
    if (!enabled) return Promise.resolve(false);

    if (wakeLockPossible) {
      return requestWakeLock().then((ok) => {
        if (ok) {
          stopFallbackVideo();
          return true;
        }
        void releaseWakeLock();
        return startFallbackVideo();
      });
    }

    void releaseWakeLock();
    return startFallbackVideo();
  }, [enabled, wakeLockPossible, requestWakeLock, stopFallbackVideo, releaseWakeLock, startFallbackVideo]);

  // Bind "tap anywhere once" listeners whenever fallback playback is blocked.
  useEffect(() => {
    if (!enabled) return;

    const shouldArmGesture = status.state === 'needs-user-gesture' && allowFallbackVideo;
    if (!shouldArmGesture) return;
    if (gestureListenerBoundRef.current) return;
    gestureListenerBoundRef.current = true;

    const onGesture = async () => {
      const ok = await startFallbackVideo();
      if (ok) {
        document.removeEventListener('click', onGesture, true);
        document.removeEventListener('touchstart', onGesture, true);
        document.removeEventListener('keydown', onGesture, true);
        gestureListenerBoundRef.current = false;
      }
    };

    document.addEventListener('click', onGesture, true);
    document.addEventListener('touchstart', onGesture, true);
    document.addEventListener('keydown', onGesture, true);

    return () => {
      gestureListenerBoundRef.current = false;
      document.removeEventListener('click', onGesture, true);
      document.removeEventListener('touchstart', onGesture, true);
      document.removeEventListener('keydown', onGesture, true);
    };
  }, [enabled, status.state, allowFallbackVideo, startFallbackVideo]);

  // Re-acquire on visibility change.
  useEffect(() => {
    if (!enabled) return;

    const onVisibility = async () => {
      if (document.visibilityState === 'visible') {
        await ensureEnabled();
      } else {
        // Be polite when hidden.
        await releaseWakeLock();
        if (fallbackVideoRef.current) {
          try { fallbackVideoRef.current.pause(); } catch {}
        }
      }
    };

    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [enabled, ensureEnabled, releaseWakeLock]);

  // Main on/off effect.
  useEffect(() => {
    void ensureEnabled();
    return () => {
      void stopAll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Defensive: stop heartbeat if we're no longer in wake-lock mode.
  useEffect(() => {
    if (!enabled) {
      stopRepaintHeartbeat();
      return;
    }
    if (status.state === 'active' && 'mode' in status && status.mode === 'wake-lock') return;
    stopRepaintHeartbeat();
  }, [enabled, status, stopRepaintHeartbeat]);

  return {
    status,
    ensureEnabled,
    enableFromUserGesture,
    stopAll,
    wakeLockPossible,
    secureContext: isSecureContextForWakeLock(),
  };
};
