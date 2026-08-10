/**
 * The pure half of the in-app update check: version comparison, release
 * parsing, asset selection and the skipped-version persistence.
 *
 * The check itself runs in the user's browser against the public GitHub
 * releases API, exactly as the project site does. The backend makes no
 * outbound request and nothing of the user's is sent: it is one anonymous
 * GET for the latest published release.
 */

export const RELEASES_PAGE_URL =
  'https://github.com/oernster/EDColonisationAsst/releases/latest';

export const RELEASES_API_URL =
  'https://api.github.com/repos/oernster/EDColonisationAsst/releases/latest';

/** The installer asset the Download button offers; the app is Windows-only. */
export const WINDOWS_ASSET_SUFFIX = '.exe';

/** Where the skipped release version persists, per browser profile. */
export const SKIPPED_UPDATE_STORAGE_KEY = 'edcaSkippedUpdateVersion';

export interface ReleaseAsset {
  name: string;
  downloadUrl: string;
}

export interface LatestRelease {
  version: string;
  pageUrl: string;
  assets: ReleaseAsset[];
}

function parsedAssets(raw: unknown): ReleaseAsset[] {
  if (!Array.isArray(raw)) return [];
  const assets: ReleaseAsset[] = [];
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue;
    const name = (entry as Record<string, unknown>).name;
    const url = (entry as Record<string, unknown>).browser_download_url;
    if (typeof name === 'string' && name && typeof url === 'string' && url) {
      assets.push({ name, downloadUrl: url });
    }
  }
  return assets;
}

/**
 * Read the latest-release payload into the shape the check needs; null
 * when any required field is missing or wrongly typed. The endpoint returns
 * only published, non-draft, non-prerelease releases, so a tag pushed
 * mid-development can never surface here.
 */
export function parseLatestRelease(payload: unknown): LatestRelease | null {
  if (typeof payload !== 'object' || payload === null) return null;
  const record = payload as Record<string, unknown>;
  const tag = record.tag_name;
  const pageUrl = record.html_url;
  if (typeof tag !== 'string' || !tag) return null;
  if (typeof pageUrl !== 'string' || !pageUrl) return null;
  return {
    version: tag.replace(/^v/i, ''),
    pageUrl,
    assets: parsedAssets(record.assets),
  };
}

/** The Windows installer asset's URL; null when the release has none. */
export function selectWindowsAssetUrl(assets: ReleaseAsset[]): string | null {
  for (const asset of assets) {
    if (asset.name.toLowerCase().endsWith(WINDOWS_ASSET_SUFFIX)) {
      return asset.downloadUrl;
    }
  }
  return null;
}

/** The skipped version; a blocked or absent storage reads as none (null). */
export function loadSkippedVersion(storage?: Storage): string | null {
  try {
    const store = storage ?? window.localStorage;
    return store.getItem(SKIPPED_UPDATE_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

/** Persist the skipped version; best effort, a blocked storage is silent. */
export function saveSkippedVersion(version: string, storage?: Storage): void {
  try {
    const store = storage ?? window.localStorage;
    store.setItem(SKIPPED_UPDATE_STORAGE_KEY, version);
  } catch {
    // A browser that blocks storage simply prompts again next session.
  }
}

/** Strip a leading v and anything after the numeric x.y.z core. */
function numericParts(version: string): number[] {
  const core = version.trim().replace(/^v/i, '').split(/[\s(+-]/)[0];
  return core.split('.').map((part) => Number.parseInt(part, 10));
}

/**
 * Whether `latest` is a strictly newer semantic version than `current`.
 * Returns false for anything unparseable, because a broken reading must
 * never nag the user to upgrade.
 */
export function isNewerVersion(latest: string, current: string): boolean {
  const a = numericParts(latest);
  const b = numericParts(current);
  if (a.length === 0 || b.length === 0) return false;
  const length = Math.max(a.length, b.length);
  for (let i = 0; i < length; i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (Number.isNaN(x) || Number.isNaN(y)) return false;
    if (x !== y) return x > y;
  }
  return false;
}
