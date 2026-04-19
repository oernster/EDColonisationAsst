import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Avoid network noise from components that load systems/health/settings.
import axios from 'axios';

// Mock API calls used by App's `loadMeta()` effect to avoid act warnings and network access.
// NOTE: `vi.mock()` is hoisted. Use `vi.hoisted()` so these are available when the mock factory runs.
const { mockHealthCheck, mockGetAppSettings } = vi.hoisted(() => {
  return {
    mockHealthCheck: vi
      .fn()
      .mockResolvedValue({ version: '2.3.1', python_version: '3.11.0' }),
    mockGetAppSettings: vi.fn().mockResolvedValue({
      inara_commander_name: 'Test Commander',
    }),
  };
});
vi.mock('./services/api', () => ({
  api: {
    healthCheck: mockHealthCheck,
    getAppSettings: mockGetAppSettings,
    // New AJAX live-update loop (long-poll). In tests we just return a stable
    // response so the background effect doesn't throw.
    longPollChanges: vi.fn().mockResolvedValue({ seq: 0, changed: false }),
    // Used by refreshFromBackend(); prevent errors if called.
    getSystems: vi.fn().mockResolvedValue([]),
    getSystemData: vi.fn().mockResolvedValue(null),
    getCurrentSystem: vi.fn().mockResolvedValue({ current_system: null }),
  },
}));

import App from './App';

describe('App', () => {
  beforeEach(() => {
    window.localStorage.clear();
    axios.get = () => Promise.reject(new Error('Network disabled in unit tests'));

    mockHealthCheck.mockClear();
    mockGetAppSettings.mockClear();
  });

  it('renders the main heading', () => {
    render(<App />);
    const headingElement = screen.getByText(/Elite: Dangerous Colonisation Assistant/i);
    expect(headingElement).toBeTruthy();
  });

  it('does not render the keep-awake chip on desktop', async () => {
    // Most test environments have a non-mobile UA; ensure it explicitly.
    Object.defineProperty(window.navigator, 'userAgent', {
      value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
      configurable: true,
    });

    render(<App />);

    // Wait for initial effects to run to avoid act warnings.
    await waitFor(() => expect(mockHealthCheck).toHaveBeenCalled());

    expect(screen.queryByText(/Keep awake:/i)).toBeNull();
  });

  it('renders the keep-awake chip on mobile/tablet and reads preference from localStorage', async () => {
    Object.defineProperty(window.navigator, 'userAgent', {
      value: 'Mozilla/5.0 (Linux; Android 14; SM-X210) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      configurable: true,
    });
    window.localStorage.setItem('edcaKeepAwakeEnabled', 'true');

    render(<App />);

    await waitFor(() => expect(mockHealthCheck).toHaveBeenCalled());

    // When enabled, the app may show "Starting" briefly while the hook runs.
    // We just assert it does not show the plain Off state.
    expect(screen.getByText(/Keep awake:/i)).toBeTruthy();
    expect(screen.queryByText(/Keep awake: Off/i)).toBeNull();
  });
});
