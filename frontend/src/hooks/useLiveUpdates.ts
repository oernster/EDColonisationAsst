/**
 * The AJAX long-poll loop that keeps the UI in step with journal ingestion.
 *
 * This replaced a WebSocket mechanism. The backend holds the request open and
 * returns when its change sequence advances, so the normal case is one blocked
 * request rather than a poll storm. Two safety nets matter here: a short sleep
 * when the backend returns immediately with changed=false (a misconfigured
 * proxy or a test double would otherwise spin the CPU), plus exponential
 * backoff when the request itself fails.
 */

import { useEffect, useRef } from 'react';

import { api } from '../services/api';
import type { SystemColonisationData } from '../types/colonisation';

const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 30000;
const IDLE_SLEEP_MS = 250;
const VISIBLE_TIMEOUT_S = 25;
const HIDDEN_TIMEOUT_S = 60;

export interface UseLiveUpdatesOptions {
  currentSystem: string | null;
  setSystemData: (data: SystemColonisationData | null) => void;
  setAllSystems: (systems: string[]) => void;
}

export function useLiveUpdates({
  currentSystem,
  setSystemData,
  setAllSystems,
}: UseLiveUpdatesOptions): void {
  // The loop below never re-subscribes, so it reads the selected system through
  // a ref rather than closing over a value that would go stale immediately.
  const currentSystemRef = useRef<string | null>(currentSystem);
  const changeSeqRef = useRef<number>(0);

  useEffect(() => {
    currentSystemRef.current = currentSystem;
  }, [currentSystem]);

  useEffect(() => {
    let cancelled = false;
    let backoffMs = INITIAL_BACKOFF_MS;

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        window.setTimeout(() => resolve(), ms);
      });

    const refreshFromBackend = async () => {
      try {
        // Refresh system list (may change after journal reloads).
        const systems = await api.getSystems();
        setAllSystems(systems);
      } catch {
        // Ignore; UI can continue with cached list.
      }

      // Refresh selected system snapshot.
      const selectedSystem = currentSystemRef.current;

      if (selectedSystem) {
        const data = await api.getSystemData(selectedSystem);
        setSystemData(data);
      }
    };

    const run = async () => {
      while (!cancelled) {
        const hidden =
          typeof document !== 'undefined' && document.visibilityState === 'hidden';
        const timeoutS = hidden ? HIDDEN_TIMEOUT_S : VISIBLE_TIMEOUT_S;

        try {
          const res = await api.longPollChanges(changeSeqRef.current, timeoutS);
          changeSeqRef.current = res.seq;
          backoffMs = INITIAL_BACKOFF_MS;

          if (res.changed) {
            await refreshFromBackend();
            // Let feature panels that are not part of refreshFromBackend
            // (e.g. Fleet carriers) react immediately.
            window.dispatchEvent(new Event('edcaBackendChanged'));
          } else {
            await sleep(IDLE_SLEEP_MS);
          }
        } catch {
          await sleep(backoffMs);
          backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
