/**
 * Checks GitHub for a newer release than the one running: once shortly
 * after load and again every 24 hours while the HUD stays open.
 *
 * The request is made by the browser, not the backend, so the backend's
 * no-outbound-requests contract holds; nothing of the user's is sent. A
 * failed or blocked check simply reports no update, because an update nag
 * must never be built on a guess. A release version the user chose to
 * skip persists in this browser's local storage and never prompts again;
 * the header control still shows it so the choice is never a dead end.
 */

import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

import {
  isNewerVersion,
  loadSkippedVersion,
  parseLatestRelease,
  RELEASES_API_URL,
  RELEASES_PAGE_URL,
  saveSkippedVersion,
  selectWindowsAssetUrl,
  type LatestRelease,
} from '../utils/updateCheck';

/** How often the open HUD re-asks GitHub, in milliseconds. */
export const RECHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;

/**
 * What a manual check concluded. Unlike the automatic check a manual one
 * reports every outcome: a malformed payload or an unknown running version
 * cannot confirm anything, so both read as unreachable rather than as a
 * false "you are up to date".
 */
export type ManualCheckOutcome = 'update' | 'latest' | 'unreachable';

export interface UpdateCheck {
  latestVersion: string | null;
  /** Newer than the running version; true even for a skipped release. */
  updateAvailable: boolean;
  /** updateAvailable minus the release the user chose to skip. */
  updateOffered: boolean;
  /** The Windows installer asset, when the release carries one. */
  downloadUrl: string | null;
  /** The human releases page; the Download fallback. */
  pageUrl: string;
  /** Persist the offered version so it never prompts again. */
  skipThisVersion: () => void;
  /** Ask GitHub right now, ignoring the skip; for a manual check. */
  checkNow: () => Promise<ManualCheckOutcome>;
}

export function useUpdateCheck(currentVersion: string | null): UpdateCheck {
  const [release, setRelease] = useState<LatestRelease | null>(null);
  const [skippedVersion, setSkippedVersion] = useState<string | null>(() =>
    loadSkippedVersion(),
  );

  useEffect(() => {
    if (!currentVersion) return;
    let cancelled = false;

    const check = () => {
      axios
        .get(RELEASES_API_URL)
        .then((response) => {
          if (cancelled) return;
          setRelease(parseLatestRelease(response.data));
        })
        .catch(() => {
          // Offline, rate-limited or blocked: no update is offered.
        });
    };

    check();
    const timer = window.setInterval(check, RECHECK_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentVersion]);

  const latestVersion = release?.version ?? null;
  const updateAvailable = Boolean(
    currentVersion &&
      latestVersion &&
      isNewerVersion(latestVersion, currentVersion),
  );
  const updateOffered = updateAvailable && latestVersion !== skippedVersion;

  const skipThisVersion = useCallback(() => {
    if (!latestVersion) return;
    saveSkippedVersion(latestVersion);
    setSkippedVersion(latestVersion);
  }, [latestVersion]);

  const checkNow = useCallback(async (): Promise<ManualCheckOutcome> => {
    if (!currentVersion) return 'unreachable';
    try {
      const response = await axios.get(RELEASES_API_URL);
      const parsed = parseLatestRelease(response.data);
      if (!parsed) return 'unreachable';
      setRelease(parsed);
      return isNewerVersion(parsed.version, currentVersion)
        ? 'update'
        : 'latest';
    } catch {
      return 'unreachable';
    }
  }, [currentVersion]);

  return {
    latestVersion,
    updateAvailable,
    updateOffered,
    downloadUrl: release ? selectWindowsAssetUrl(release.assets) : null,
    pageUrl: release?.pageUrl ?? RELEASES_PAGE_URL,
    skipThisVersion,
    checkNow,
  };
}
