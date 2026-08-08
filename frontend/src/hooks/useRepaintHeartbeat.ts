import { useCallback, useEffect, useRef } from 'react';

import { isMobileOrTabletLike } from './keepAwakeCapabilities';

/**
 * A compositor heartbeat to run alongside a held Wake Lock.
 *
 * Some mobile and tablet browsers honour a screen Wake Lock yet still let the
 * compositor idle, so the screen dims with the lock held. Writing a fresh
 * transform on the body gives it something to do. What it does is device
 * agnostic; it is armed only where that failure is seen, so a desktop is left
 * alone.
 *
 * Whether to arm is decided once on mount rather than per call, because the
 * probe reads the screen and the pointer, neither of which changes under us.
 */

const HEARTBEAT_INTERVAL_MS = 2000;

/** Sub-pixel, so each nudge is a new transform value but moves nothing. */
const HEARTBEAT_MAX_NUDGE_PX = 0.0001;

export const useRepaintHeartbeat = () => {
  const armedRef = useRef(false);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    armedRef.current = isMobileOrTabletLike();
  }, []);

  const start = useCallback(() => {
    if (!armedRef.current) return;
    if (intervalRef.current !== null) return;

    intervalRef.current = window.setInterval(() => {
      try {
        document.body.style.transform =
          `translateZ(${Math.random() * HEARTBEAT_MAX_NUDGE_PX}px)`;
      } catch {
        // ignore
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, []);

  const stop = useCallback(() => {
    if (intervalRef.current === null) return;
    try {
      window.clearInterval(intervalRef.current);
    } catch {
      // ignore
    } finally {
      intervalRef.current = null;
    }
    try {
      document.body.style.transform = '';
    } catch {
      // ignore
    }
  }, []);

  return { start, stop };
};
