/**
 * The user's keep-awake preference and the events that change it.
 *
 * Distinct from useKeepAwake, which owns the Wake Lock itself: this hook only
 * answers "should we be trying". It defaults on for mobile and tablet without
 * ever overriding an explicit choice; it listens for both the custom event
 * the Settings page fires and the storage event another tab produces.
 */

import { useEffect, useState } from 'react';

import { isMobileOrTablet } from '../utils/device';

const STORAGE_KEY = 'edcaKeepAwakeEnabled';

export function readKeepAwakeEnabled(): boolean {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === 'true') return true;
    if (raw === 'false') return false;
    // Default ON for mobile/tablet but never over an explicit user choice.
    return isMobileOrTablet();
  } catch {
    return isMobileOrTablet();
  }
}

export function useKeepAwakePreference(): boolean {
  // Initialise from localStorage synchronously to avoid a "flash" of Off in tests/UI.
  const [keepAwakeEnabled, setKeepAwakeEnabled] = useState<boolean>(() =>
    readKeepAwakeEnabled(),
  );

  useEffect(() => {
    // Persist the default for mobile/tablet so the behaviour is stable.
    try {
      const existing = window.localStorage.getItem(STORAGE_KEY);
      if (existing === null) {
        window.localStorage.setItem(STORAGE_KEY, String(readKeepAwakeEnabled()));
      }
    } catch {
      // Ignore.
    }

    const onLocalPreferenceChanged = () => {
      setKeepAwakeEnabled(readKeepAwakeEnabled());
    };

    // Custom event fired by Settings when toggled.
    window.addEventListener('edcaKeepAwakeChanged', onLocalPreferenceChanged);
    // Also respond to cross-tab changes.
    window.addEventListener('storage', onLocalPreferenceChanged);

    return () => {
      window.removeEventListener('edcaKeepAwakeChanged', onLocalPreferenceChanged);
      window.removeEventListener('storage', onLocalPreferenceChanged);
    };
  }, []);

  return keepAwakeEnabled;
}
