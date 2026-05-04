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
import { useColonisationStore } from './stores/colonisationStore';
import { CommodityStatus, SystemColonisationData } from './types/colonisation';
import { SiteList } from './components/SiteList/SiteList';

describe('App', () => {
  beforeEach(() => {
    window.localStorage.clear();
    axios.get = () => Promise.reject(new Error('Network disabled in unit tests'));

    mockHealthCheck.mockClear();
    mockGetAppSettings.mockClear();

    // Reset global zustand store state between tests.
    useColonisationStore.setState({
      currentSystem: null,
      systemData: null,
      allSystems: [],
      loading: false,
      error: null,
      currentSystemInfo: null,
      settingsVersion: 0,
    });
  });

  it('renders the main heading', () => {
    render(<App />);
    const headingElement = screen.getByText(/Elite: Dangerous Colonisation Assistant/i);
    expect(headingElement).toBeTruthy();
  });

  it('includes Completed Stations as a System View sub-tab', () => {
    const systemData: SystemColonisationData = {
      system_name: 'Sol',
      total_sites: 1,
      completed_sites: 1,
      in_progress_sites: 0,
      completion_percentage: 100,
      construction_sites: [
        {
          market_id: 1,
          station_name: 'Galileo',
          station_type: 'Construction Depot',
          system_name: 'Sol',
          system_address: 123,
          construction_progress: 100,
          construction_complete: true,
          construction_failed: false,
          commodities: [
            {
              name: 'foodcartridges',
              name_localised: 'Food Cartridges',
              required_amount: 10,
              provided_amount: 10,
              payment: 1000,
              remaining_amount: 0,
              progress_percentage: 100,
              status: CommodityStatus.COMPLETED,
            },
          ],
          last_updated: '2026-04-29T00:00:00.000Z',
          is_complete: true,
          total_commodities_needed: 0,
          commodities_progress_percentage: 100,
          last_source: 'journal',
        },
      ],
    };

    useColonisationStore.setState({
      currentSystem: 'Sol',
      systemData,
      loading: false,
      error: null,
    });

    render(<App />);

    // System View is the default top-level tab. Verify the new sub-tab label exists.
    expect(screen.getByRole('tab', { name: /Completed Stations/i })).toBeTruthy();
  });

  it('computes per-site live progress from total commodity delivery (sum provided / sum required)', () => {
    const systemData: SystemColonisationData = {
      system_name: 'Sol',
      total_sites: 1,
      completed_sites: 0,
      in_progress_sites: 1,
      completion_percentage: 0,
      construction_sites: [
        {
          market_id: 42,
          station_name: 'Orbital Construction Site: Example',
          station_type: 'Construction Depot',
          system_name: 'Sol',
          system_address: 123,
          // Deliberately set to an incorrect value to ensure we are NOT using it.
          construction_progress: 0,
          construction_complete: false,
          construction_failed: false,
          commodities: [
            {
              name: 'water',
              name_localised: 'Water',
              required_amount: 4,
              provided_amount: 2,
              payment: 1000,
              remaining_amount: 2,
              progress_percentage: 50,
              status: CommodityStatus.IN_PROGRESS,
            },
            {
              name: 'liquidoxygen',
              name_localised: 'Liquid Oxygen',
              required_amount: 4,
              provided_amount: 2,
              payment: 1000,
              remaining_amount: 2,
              progress_percentage: 50,
              status: CommodityStatus.IN_PROGRESS,
            },
          ],
          last_updated: '2026-04-29T00:00:00.000Z',
          is_complete: false,
          total_commodities_needed: 4,
          commodities_progress_percentage: 50,
          last_source: 'journal',
        },
      ],
    };

    useColonisationStore.setState({
      currentSystem: 'Sol',
      systemData,
      loading: false,
      error: null,
    });

    render(<SiteList viewMode="stations" />);

    // 2/4 + 2/4 => 4/8 => 50%
    expect(screen.getByTestId('site-progress-label-42').textContent).toContain('50.0%');
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
