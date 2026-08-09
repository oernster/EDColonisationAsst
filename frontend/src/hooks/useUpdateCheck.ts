/**
 * Checks GitHub once per session for a newer release than the one running.
 *
 * The request is made by the browser, not the backend, so the backend's
 * no-outbound-requests contract holds; nothing of the user's is sent. A
 * failed or blocked check simply reports no update, because an update nag
 * must never be built on a guess.
 */

import { useEffect, useState } from 'react';
import axios from 'axios';

import { isNewerVersion, RELEASES_API_URL } from '../utils/updateCheck';

export interface UpdateCheck {
  latestVersion: string | null;
  updateAvailable: boolean;
}

export function useUpdateCheck(currentVersion: string | null): UpdateCheck {
  const [latestVersion, setLatestVersion] = useState<string | null>(null);

  useEffect(() => {
    if (!currentVersion) return;
    let cancelled = false;

    axios
      .get(RELEASES_API_URL)
      .then((response) => {
        if (cancelled) return;
        const tag = (response.data?.tag_name ?? '').replace(/^v/i, '');
        setLatestVersion(tag || null);
      })
      .catch(() => {
        // Offline, rate-limited or blocked: no update is offered.
      });

    return () => {
      cancelled = true;
    };
  }, [currentVersion]);

  const updateAvailable = Boolean(
    currentVersion && latestVersion && isNewerVersion(latestVersion, currentVersion),
  );

  return { latestVersion, updateAvailable };
}
