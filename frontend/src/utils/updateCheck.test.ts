import { describe, expect, it } from 'vitest';

import {
  isNewerVersion,
  loadSkippedVersion,
  parseLatestRelease,
  saveSkippedVersion,
  selectWindowsAssetUrl,
  SKIPPED_UPDATE_STORAGE_KEY,
} from './updateCheck';

describe('isNewerVersion', () => {
  it('detects a newer major, minor and patch', () => {
    expect(isNewerVersion('4.0.0', '3.1.0')).toBe(true);
    expect(isNewerVersion('3.2.0', '3.1.0')).toBe(true);
    expect(isNewerVersion('3.1.1', '3.1.0')).toBe(true);
  });

  it('is false for equal or older versions', () => {
    expect(isNewerVersion('3.1.0', '3.1.0')).toBe(false);
    expect(isNewerVersion('3.0.9', '3.1.0')).toBe(false);
    expect(isNewerVersion('2.9.9', '3.0.0')).toBe(false);
  });

  it('tolerates a v prefix and a build suffix', () => {
    expect(isNewerVersion('v3.2.0', '3.1.0 (20260809)')).toBe(true);
    expect(isNewerVersion('v3.1.0', '3.1.0 (20260809)')).toBe(false);
  });

  it('handles differing segment counts numerically', () => {
    expect(isNewerVersion('3.1', '3.1.0')).toBe(false);
    expect(isNewerVersion('3.1.0.1', '3.1.0')).toBe(true);
  });

  it('never reports an update on an unparseable reading', () => {
    expect(isNewerVersion('', '3.1.0')).toBe(false);
    expect(isNewerVersion('latest', '3.1.0')).toBe(false);
    expect(isNewerVersion('3.2.0', 'unknown')).toBe(false);
  });
});

describe('parseLatestRelease', () => {
  const payload = {
    tag_name: 'v3.2.0',
    html_url: 'https://example.test/rel',
    assets: [
      { name: 'EDColonisationAsstSetup.exe', browser_download_url: 'https://example.test/win' },
    ],
  };

  it('reads a valid payload and strips the v prefix', () => {
    expect(parseLatestRelease(payload)).toEqual({
      version: '3.2.0',
      pageUrl: 'https://example.test/rel',
      assets: [
        { name: 'EDColonisationAsstSetup.exe', downloadUrl: 'https://example.test/win' },
      ],
    });
  });

  it('rejects a payload missing or mistyping its required fields', () => {
    expect(parseLatestRelease(null)).toBeNull();
    expect(parseLatestRelease([1, 2])).toBeNull();
    expect(parseLatestRelease({ ...payload, tag_name: '' })).toBeNull();
    expect(parseLatestRelease({ ...payload, tag_name: 7 })).toBeNull();
    expect(parseLatestRelease({ ...payload, html_url: '' })).toBeNull();
    expect(parseLatestRelease({ ...payload, html_url: 7 })).toBeNull();
  });

  it('drops malformed assets and tolerates a missing list', () => {
    const messy = parseLatestRelease({
      ...payload,
      assets: [
        'not an object',
        { name: '', browser_download_url: 'https://example.test/x' },
        { name: 'no-url.exe' },
        { name: 'good.exe', browser_download_url: 'https://example.test/g' },
      ],
    });
    expect(messy?.assets).toEqual([
      { name: 'good.exe', downloadUrl: 'https://example.test/g' },
    ]);
    expect(parseLatestRelease({ ...payload, assets: undefined })?.assets).toEqual([]);
    expect(parseLatestRelease({ ...payload, assets: 'nope' })?.assets).toEqual([]);
  });
});

describe('selectWindowsAssetUrl', () => {
  it('picks the .exe asset case-insensitively, else null', () => {
    expect(
      selectWindowsAssetUrl([
        { name: 'notes.txt', downloadUrl: 'https://example.test/t' },
        { name: 'Setup.EXE', downloadUrl: 'https://example.test/w' },
      ]),
    ).toBe('https://example.test/w');
    expect(selectWindowsAssetUrl([])).toBeNull();
    expect(
      selectWindowsAssetUrl([{ name: 'app.dmg', downloadUrl: 'https://example.test/m' }]),
    ).toBeNull();
  });
});

describe('skipped version persistence', () => {
  function fakeStorage(initial: Record<string, string> = {}): Storage {
    const data = new Map(Object.entries(initial));
    return {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => void data.set(key, value),
      removeItem: (key: string) => void data.delete(key),
      clear: () => data.clear(),
      key: () => null,
      get length() {
        return data.size;
      },
    } as Storage;
  }

  it('round-trips through the storage key', () => {
    const storage = fakeStorage();
    expect(loadSkippedVersion(storage)).toBeNull();
    saveSkippedVersion('3.2.0', storage);
    expect(storage.getItem(SKIPPED_UPDATE_STORAGE_KEY)).toBe('3.2.0');
    expect(loadSkippedVersion(storage)).toBe('3.2.0');
  });

  it('reads a blocked or empty storage as no skip', () => {
    const blocked = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    } as unknown as Storage;
    expect(loadSkippedVersion(blocked)).toBeNull();
    expect(() => saveSkippedVersion('3.2.0', blocked)).not.toThrow();
    expect(loadSkippedVersion(fakeStorage({ other: 'x' }))).toBeNull();
  });
});
