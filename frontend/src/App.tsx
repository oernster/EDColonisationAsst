import { useState } from 'react';
import {
  ThemeProvider,
  CssBaseline,
  Container,
  Box,
  Typography,
  Tabs,
  Tab,
  Button,
  Tooltip,
} from '@mui/material';

import { SystemSelector } from './components/SystemSelector/SystemSelector';
import { SiteList } from './components/SiteList/SiteList';
import { FleetCarriersPanel } from './components/FleetCarriers/FleetCarriersPanel';
import { SettingsPage } from './components/Settings/SettingsPage';
import { AboutPanel } from './components/About/AboutPanel';
import { LicensePanel } from './components/About/LicensePanel';
import { KeepAwakeChip } from './components/KeepAwake/KeepAwakeChip';
import { useColonisationStore } from './stores/colonisationStore';
import { useKeepAwake } from './hooks/useKeepAwake';
import { useKeepAwakePreference } from './hooks/useKeepAwakePreference';
import { ThemeMode, useThemeMode } from './hooks/useThemeMode';
import { useLiveUpdates } from './hooks/useLiveUpdates';
import { useBackendMeta } from './hooks/useBackendMeta';
import { describeLocation, formatCredits } from './utils/commanderStatus';
import { useUpdateCheck } from './hooks/useUpdateCheck';
import { RELEASES_PAGE_URL } from './utils/updateCheck';
import { darkTheme, lightTheme } from './theme';
// Generated from the single master badge by generate_icons.py at the repo root.
// Imported rather than read from public/ so Vite fingerprints it and a missing
// file fails the build instead of rendering as a broken image at runtime.
import edcaIcon from './assets/edca-icon.png';

// The header badge sits beside the h3 title, so it is sized to that line rather
// than to the asset: the file is written at twice this so it stays sharp on a
// high-DPI display or a tablet.
const HEADER_ICON_PX = 96;
// On phone-width screens the header stacks, so the badge drops a size to
// leave the room to the title.
const HEADER_ICON_PX_SMALL = 64;

const THEME_BUTTON_SX = {
  minWidth: 36,
  width: 36,
  height: 36,
  borderRadius: 1,
  padding: 0,
  lineHeight: 1,
};

function App() {
  const {
    currentSystem,
    systemData,
    loading,
    error,
    settingsVersion,
    setSystemData,
    setAllSystems,
  } = useColonisationStore();

  const [currentTab, setCurrentTab] = useState(0);
  const [systemViewTab, setSystemViewTab] = useState(0);

  const { themeMode, setThemeModeAndPersist } = useThemeMode();
  const keepAwakeEnabled = useKeepAwakePreference();
  const { appVersion, appVersionRaw, pythonVersion, healthError, commanderStatus } =
    useBackendMeta(settingsVersion);
  const commanderName = commanderStatus?.commander_name ?? null;
  const commanderCredits = commanderStatus?.credits_balance ?? null;
  const commanderLocation = commanderStatus ? describeLocation(commanderStatus) : null;
  const { latestVersion, updateAvailable } = useUpdateCheck(appVersionRaw);

  useLiveUpdates({ currentSystem, setSystemData, setAllSystems });

  const {
    status: keepAwakeStatus,
    wakeLockPossible,
    secureContext,
    enableFromUserGesture,
  } = useKeepAwake({
    enabled: keepAwakeEnabled,
    allowFallbackVideo: keepAwakeEnabled,
  });

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setCurrentTab(newValue);
  };

  const handleSystemViewTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setSystemViewTab(newValue);
  };

  const theme = themeMode === 'dark' ? darkTheme : lightTheme;
  const nextThemeMode: ThemeMode = themeMode === 'dark' ? 'light' : 'dark';

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Container maxWidth="xl">
        <Box sx={{ py: 4 }}>
          {/* Header */}
          {/* Explicit layout per breakpoint rather than flex wrapping: a
              wrapped right-aligned block reads as broken on tablets, so below
              md the header is a left-aligned column and from md up the
              commander block sits beside the title, right-aligned. */}
          <Box
            sx={{
              mb: 4,
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: 2,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 0 }}>
              <Box
                component="img"
                src={edcaIcon}
                alt=""
                sx={{
                  width: { xs: HEADER_ICON_PX_SMALL, sm: HEADER_ICON_PX },
                  height: { xs: HEADER_ICON_PX_SMALL, sm: HEADER_ICON_PX },
                  flexShrink: 0,
                }}
              />
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="h3"
                  component="h1"
                  gutterBottom
                  sx={{
                    color: 'primary.main',
                    fontWeight: 'bold',
                    // Scaled to the viewport so the md+ side-by-side row fits
                    // and the stacked tablet/phone layouts are not dominated
                    // by the title.
                    fontSize: { xs: '1.75rem', sm: '2.125rem', lg: '3rem' },
                  }}
                >
                  Elite: Dangerous Colonisation Assistant
                </Typography>
                <Typography variant="subtitle1" color="text.secondary">
                  Real-time tracking for colonisation efforts
                </Typography>
              </Box>
            </Box>
            <Box sx={{ textAlign: { xs: 'left', md: 'right' }, minWidth: 0 }}>
              <Typography variant="body2" sx={{ color: 'primary.main' }}>
                Commander:
              </Typography>
              <Typography variant="body1" fontWeight="medium" color="text.primary">
                {commanderName || 'Unknown'}
              </Typography>
              {commanderCredits !== null && (
                <Typography variant="body2" color="text.secondary">
                  {formatCredits(commanderCredits)}
                </Typography>
              )}
              {commanderLocation && (
                <Typography variant="body2" color="text.secondary">
                  {commanderLocation}
                </Typography>
              )}
              {!commanderName && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: 'block', mt: 0.5 }}
                >
                  Detected automatically from your journal files.
                </Typography>
              )}
              <Box
                sx={{
                  mt: 1,
                  display: 'flex',
                  justifyContent: { xs: 'flex-start', md: 'flex-end' },
                  gap: 1,
                  alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
                {updateAvailable && latestVersion && (
                  <Tooltip title="A newer release is on GitHub. Opens the releases page; run the installer over this installation to upgrade.">
                    <Button
                      size="small"
                      variant="outlined"
                      color="warning"
                      href={RELEASES_PAGE_URL}
                      target="_blank"
                      rel="noopener"
                    >
                      Update available: v{latestVersion}
                    </Button>
                  </Tooltip>
                )}
                <KeepAwakeChip
                  enabled={keepAwakeEnabled}
                  status={keepAwakeStatus}
                  wakeLockPossible={wakeLockPossible}
                  secureContext={secureContext}
                  onEnableFromUserGesture={() => {
                    void enableFromUserGesture();
                  }}
                />
                {/* One control, not two. It shows the theme it will switch
                    TO, so the icon is the choice on offer rather than a
                    reading of the state you are already looking at. */}
                <Tooltip title={`Switch to ${nextThemeMode} theme`}>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => setThemeModeAndPersist(nextThemeMode)}
                    sx={THEME_BUTTON_SX}
                    aria-label={`Switch to ${nextThemeMode} theme`}
                  >
                    {nextThemeMode === 'light' ? '☀️' : '🌙'}
                  </Button>
                </Tooltip>
              </Box>
            </Box>
          </Box>

          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={currentTab} onChange={handleTabChange} aria-label="nav tabs">
              <Tab label="System View" />
              <Tab label="Settings" />
              <Tab label="About" />
              <Tab label="License" />
            </Tabs>
          </Box>

          {currentTab === 0 && (
            <Box sx={{ pt: 4 }}>
              {/* System Selector */}
              <Box sx={{ mb: 4 }}>
                <SystemSelector />
              </Box>

              {/* Error Display */}
              {error && (
                <Box sx={{ mb: 4, p: 2, bgcolor: 'error.dark', borderRadius: 1 }}>
                  <Typography color="error.contrastText">{error}</Typography>
                </Box>
              )}

              {/* Loading State */}
              {loading && (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography>Loading colonisation data...</Typography>
                </Box>
              )}

              {/* Site List */}
              {!loading && currentSystem && systemData && (
                <>
                  <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
                    <Tabs
                      value={systemViewTab}
                      onChange={handleSystemViewTabChange}
                      aria-label="system view detail tabs"
                      textColor="primary"
                      indicatorColor="primary"
                    >
                      <Tab label="System Commodities" />
                      <Tab label="Stations" />
                      <Tab label="Completed Stations" />
                      <Tab label="Fleet carriers" />
                    </Tabs>
                  </Box>

                  {systemViewTab === 0 && <SiteList viewMode="system" />}
                  {systemViewTab === 1 && <SiteList viewMode="stations" />}
                  {systemViewTab === 2 && <SiteList viewMode="completed_stations" />}
                  {systemViewTab === 3 && <FleetCarriersPanel />}
                </>
              )}

              {/* Empty State */}
              {!loading && !currentSystem && !error && (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <Typography variant="h6" color="text.secondary">
                    Select a system to view colonisation progress
                  </Typography>
                </Box>
              )}
            </Box>
          )}

          {currentTab === 1 && (
            <Box sx={{ pt: 4 }}>
              <SettingsPage />
            </Box>
          )}

          {currentTab === 2 && (
            <AboutPanel
              appVersion={appVersion}
              pythonVersion={pythonVersion}
              healthError={healthError}
            />
          )}

          {currentTab === 3 && <LicensePanel />}
        </Box>
      </Container>
    </ThemeProvider>
  );
}

export default App;
