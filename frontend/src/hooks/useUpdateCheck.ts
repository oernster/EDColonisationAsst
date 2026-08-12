/**
 * Asks GitHub for the latest release, but only when the user asks first.
 *
 * There is deliberately no timer here. EDCA checks automatically in exactly
 * one place, the tray, because that is the machine EDCA is installed on: this
 * HUD is meant to be read from a tablet on the local network, where an offer
 * would hand a Windows installer to something that cannot run it. Two
 * surfaces checking on their own timing also meant one release could raise
 * two prompts, each with a skip the other could not see.
 *
 * So this is the manual half. The request is made by the browser rather than
 * the backend and nothing of the user's is sent. A failed or blocked check
 * reports unreachable rather than "up to date", because an answer must never
 * be built on a guess.
 */

import { useCallback, useState } from 'react';
import axios from 'axios';

import {
  isNewerVersion,
  parseLatestRelease,
  RELEASES_API_URL,
  RELEASES_PAGE_URL,
  selectWindowsAssetUrl,
  type LatestRelease,
} from '../utils/updateCheck';

/**
 * What a check concluded. A malformed payload or an unknown running version
 * cannot confirm anything, so both read as unreachable rather than as a
 * false "you are up to date".
 */
export type ManualCheckOutcome = 'update' | 'latest' | 'unreachable';

export interface UpdateCheck {
  latestVersion: string | null;
  /** Newer than the running version, as of the last check the user ran. */
  updateAvailable: boolean;
  /** The Windows installer asset, when the release carries one. */
  downloadUrl: string | null;
  /** The human releases page; the Download fallback. */
  pageUrl: string;
  /** Ask GitHub right now. */
  checkNow: () => Promise<ManualCheckOutcome>;
}

export function useUpdateCheck(currentVersion: string | null): UpdateCheck {
  const [release, setRelease] = useState<LatestRelease | null>(null);

  const latestVersion = release?.version ?? null;
  const updateAvailable = Boolean(
    currentVersion &&
      latestVersion &&
      isNewerVersion(latestVersion, currentVersion),
  );

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
    downloadUrl: release ? selectWindowsAssetUrl(release.assets) : null,
    pageUrl: release?.pageUrl ?? RELEASES_PAGE_URL,
    checkNow,
  };
}
