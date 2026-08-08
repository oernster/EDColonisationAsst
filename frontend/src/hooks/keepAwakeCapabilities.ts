/**
 * Capability probes for keep-awake.
 *
 * These answer the three questions the hook asks before it can pick a
 * strategy: is there a Wake Lock API at all, is this a context allowed to use
 * one and does the device look like something whose compositor needs a nudge.
 * They are pure reads of the environment holding no state of their own, which
 * is why they sit outside the hook and can be tested without rendering.
 */

// Types are not always present in TS lib.dom depending on config.
export type WakeLockSentinelLike = {
  released: boolean;
  release: () => Promise<void>;
  addEventListener?: (type: string, listener: () => void) => void;
  removeEventListener?: (type: string, listener: () => void) => void;
};

export type WakeLockLike = {
  request: (type: 'screen') => Promise<WakeLockSentinelLike>;
};

/**
 * Largest smaller-screen-dimension still treated as handheld. Above this, a
 * touch screen is more likely a desktop monitor than a tablet.
 */
const HANDHELD_MAX_MIN_DIMENSION_PX = 1400;

/** The Wake Lock API where the browser has one, otherwise undefined. */
export const getWakeLock = (): WakeLockLike | undefined =>
  (navigator as unknown as { wakeLock?: WakeLockLike }).wakeLock;

export const canUseWakeLock = (): boolean => {
  const wakeLock = getWakeLock();
  return typeof window !== 'undefined' && !!wakeLock && typeof wakeLock.request === 'function';
};

export const isSecureContextForWakeLock = (): boolean => {
  // Wake Lock requires a secure context (https or localhost).
  return typeof window !== 'undefined' && (window.isSecureContext ?? false);
};

/**
 * Generic "tablet-ish" heuristic.
 * We keep this conservative:
 * - Prefer UA-CH mobile flag (where available)
 * - Otherwise rely on coarse pointer / touch / screen size
 */
export const isMobileOrTabletLike = (): boolean => {
  if (typeof window === 'undefined') return false;

  const nav = navigator as unknown as { userAgentData?: { mobile?: boolean } };
  if (typeof nav.userAgentData?.mobile === 'boolean') return nav.userAgentData.mobile;

  const hasTouch =
    'ontouchstart' in window || (navigator.maxTouchPoints ?? 0) > 0;

  const coarsePointer = typeof window.matchMedia === 'function'
    ? window.matchMedia('(pointer: coarse)').matches
    : false;

  // Use viewport as a soft hint (avoids classifying small desktop windows).
  const minDim = Math.min(window.screen?.width ?? 0, window.screen?.height ?? 0);
  const screenLooksHandheld = minDim > 0 && minDim <= HANDHELD_MAX_MIN_DIMENSION_PX;

  return (hasTouch || coarsePointer) && screenLooksHandheld;
};
