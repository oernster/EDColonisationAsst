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
import { darkTheme, lightTheme } from './theme';

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
  const { appVersion, pythonVersion, healthError, commanderName } =
    useBackendMeta(settingsVersion);

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
          <Box
            sx={{
              mb: 4,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              flexWrap: 'wrap',
              gap: 2,
            }}
          >
            <Box>
              <Typography
                variant="h3"
                component="h1"
                gutterBottom
                sx={{ color: 'primary.main', fontWeight: 'bold' }}
              >
                Elite: Dangerous Colonisation Assistant
              </Typography>
              <Typography variant="subtitle1" color="text.secondary">
                Real-time tracking for colonisation efforts
              </Typography>
            </Box>
            <Box sx={{ textAlign: { xs: 'left', sm: 'right' } }}>
              <Typography variant="body2" sx={{ color: 'primary.main' }}>
                Commander:
              </Typography>
              <Typography variant="body1" fontWeight="medium" color="text.primary">
                {commanderName || 'Unknown'}
              </Typography>
              {!commanderName && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: 'block', mt: 0.5 }}
                >
                  Set your commander name in the Settings tab.
                </Typography>
              )}
              <Box
                sx={{
                  mt: 1,
                  display: 'flex',
                  justifyContent: { xs: 'flex-start', sm: 'flex-end' },
                  gap: 1,
                  alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
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
