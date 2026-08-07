/**
 * Theme mode, remembered across sessions.
 *
 * The default is dark; a stored choice wins. Persistence failures are
 * swallowed on purpose: a browser with localStorage disabled should still be
 * able to switch theme for the current session.
 */

import { useEffect, useState } from 'react';

export type ThemeMode = 'dark' | 'light';

const STORAGE_KEY = 'edcaThemeMode';

export interface UseThemeModeResult {
  themeMode: ThemeMode;
  setThemeModeAndPersist: (next: ThemeMode) => void;
}

export function useThemeMode(): UseThemeModeResult {
  const [themeMode, setThemeMode] = useState<ThemeMode>('dark');

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === 'dark' || saved === 'light') {
        setThemeMode(saved);
      }
    } catch {
      // If localStorage is unavailable, just stick with the default.
    }
  }, []);

  const setThemeModeAndPersist = (next: ThemeMode) => {
    setThemeMode(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Ignore persistence errors; theme will still switch for this session.
    }
  };

  return { themeMode, setThemeModeAndPersist };
}
