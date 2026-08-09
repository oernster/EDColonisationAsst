/**
 * Version comparison for the in-app update check.
 *
 * The check itself runs in the user's browser against the public GitHub
 * releases API, exactly as the project site does. The backend makes no
 * outbound request and nothing of the user's is sent: it is one anonymous
 * GET for the latest release tag.
 */

export const RELEASES_PAGE_URL =
  'https://github.com/oernster/EDColonisationAsst/releases/latest';

export const RELEASES_API_URL =
  'https://api.github.com/repos/oernster/EDColonisationAsst/releases/latest';

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
