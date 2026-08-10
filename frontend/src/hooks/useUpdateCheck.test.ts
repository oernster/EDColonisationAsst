import { act, renderHook, waitFor } from '@testing-library/react';
import axios from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useUpdateCheck } from './useUpdateCheck';

function releasePayload(tag: string) {
  return {
    tag_name: tag,
    html_url: 'https://example.test/rel',
    assets: [
      {
        name: 'EDColonisationAsstInstaller.exe',
        browser_download_url: 'https://example.test/win.exe',
      },
    ],
  };
}

describe('useUpdateCheck checkNow', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('reports an update when the release is newer', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: releasePayload('v3.3.0') });
    const { result } = renderHook(() => useUpdateCheck('3.2.0'));
    let outcome = '';
    await act(async () => {
      outcome = await result.current.checkNow();
    });
    expect(outcome).toBe('update');
    await waitFor(() => expect(result.current.latestVersion).toBe('3.3.0'));
    expect(result.current.downloadUrl).toBe('https://example.test/win.exe');
  });

  it('reports an update even for a skipped release', async () => {
    window.localStorage.setItem('edcaSkippedUpdateVersion', '3.3.0');
    vi.spyOn(axios, 'get').mockResolvedValue({ data: releasePayload('v3.3.0') });
    const { result } = renderHook(() => useUpdateCheck('3.2.0'));
    let outcome = '';
    await act(async () => {
      outcome = await result.current.checkNow();
    });
    expect(outcome).toBe('update');
    await waitFor(() => expect(result.current.updateOffered).toBe(false));
  });

  it('reports latest when nothing newer exists', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: releasePayload('v3.2.0') });
    const { result } = renderHook(() => useUpdateCheck('3.2.0'));
    let outcome = '';
    await act(async () => {
      outcome = await result.current.checkNow();
    });
    expect(outcome).toBe('latest');
  });

  it('reports unreachable on a network failure', async () => {
    vi.spyOn(axios, 'get').mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useUpdateCheck('3.2.0'));
    let outcome = '';
    await act(async () => {
      outcome = await result.current.checkNow();
    });
    expect(outcome).toBe('unreachable');
  });

  it('reports unreachable on a malformed payload', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { nothing: true } });
    const { result } = renderHook(() => useUpdateCheck('3.2.0'));
    let outcome = '';
    await act(async () => {
      outcome = await result.current.checkNow();
    });
    expect(outcome).toBe('unreachable');
  });

  it('reports unreachable when the running version is unknown', async () => {
    const get = vi.spyOn(axios, 'get').mockResolvedValue({
      data: releasePayload('v3.3.0'),
    });
    const { result } = renderHook(() => useUpdateCheck(null));
    let outcome = '';
    await act(async () => {
      outcome = await result.current.checkNow();
    });
    expect(outcome).toBe('unreachable');
    // With no version to compare against, GitHub is not even asked.
    expect(get).not.toHaveBeenCalled();
  });
});
