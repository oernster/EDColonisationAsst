import { useState, useEffect } from 'react';
import { Box, Typography, TextField, Button, Paper, CircularProgress, Alert, Checkbox, FormControlLabel, Divider } from '@mui/material';
import { api } from '../../services/api';
import { AppSettings } from '../../types/settings';
import { useColonisationStore } from '../../stores/colonisationStore';
import { isMobileOrTablet } from '../../utils/device';

// Only a last resort for the hints below, when the page is opened from
// somewhere without a port in its address. The served port is authoritative.
// Must match DEFAULT_BACKEND_PORT in backend/src/utils/ports.py.
const DEFAULT_BACKEND_PORT = '47021';

export const SettingsPage = () => {
  const { updateSettings } = useColonisationStore();
  const [settings, setSettings] = useState<AppSettings>({
    journal_directory: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // --- Keep-awake (browser-side) ---
  const keepAwakeStorageKey = 'edcaKeepAwakeEnabled';
  const [keepAwakeEnabled, setKeepAwakeEnabled] = useState<boolean>(() => {
    try {
      const raw = window.localStorage.getItem(keepAwakeStorageKey);
      if (raw === 'true') return true;
      if (raw === 'false') return false;
      return isMobileOrTablet();
    } catch {
      return isMobileOrTablet();
    }
  });

  // Read from the address actually being served rather than hardcoded: the
  // backend picks its port at startup and falls back to another when the
  // configured one cannot be bound, so a fixed number here would show the
  // user an address that does not answer.
  const backendPort = window.location.port || DEFAULT_BACKEND_PORT;
  const currentHost = window.location.hostname || 'localhost';
  const localUrl = `http://127.0.0.1:${backendPort}/app/`;
  const lanUrlHint =
    currentHost !== 'localhost' && currentHost !== '127.0.0.1'
      ? `http://${currentHost}:${backendPort}/app/`
      : `http://<your-PC-LAN-IP>:${backendPort}/app/`;

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        setLoading(true);
        const fetchedSettings = await api.getAppSettings();
        setSettings(fetchedSettings);
      } catch {
        setError('Failed to load settings.');
      } finally {
        setLoading(false);
      }
    };

    fetchSettings();
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      await api.updateAppSettings(settings);
      setSuccess('Settings saved successfully!');
      updateSettings();
    } catch {
      setError('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSettings({
      ...settings,
      [e.target.name]: e.target.value,
    });
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Paper sx={{ p: 3, mt: 4 }}>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      <Box component="form" noValidate autoComplete="off">
        <Typography variant="h6" gutterBottom sx={{ mt: 1 }}>
          Display / Power
        </Typography>
        <FormControlLabel
          control={
            <Checkbox
              name="keep_awake"
              color="primary"
              checked={keepAwakeEnabled}
              onChange={(e) => {
                const next = e.target.checked;
                setKeepAwakeEnabled(next);
                try {
                  window.localStorage.setItem(keepAwakeStorageKey, String(next));
                } catch {
                  // Ignore.
                }
                // Notify App.tsx to re-read local preference immediately.
                window.dispatchEvent(new Event('edcaKeepAwakeChanged'));

                // If enabling, also attempt to start immediately while we're in a user gesture.
                // If the browser still blocks autoplay, the header chip will show "Tap to enable"
                // and the user can tap the chip (or anywhere) once.
                if (next) {
                  window.dispatchEvent(new Event('edcaKeepAwakeTryEnableNow'));
                }
              }}
            />
          }
          label={
            <Typography variant="body2">
              Keep screen awake while EDCA is open (recommended for tablets)
            </Typography>
          }
          sx={{ alignItems: 'center', mb: 0.5 }}
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
          EDCA will attempt the browser Screen Wake Lock API when available (requires HTTPS or
          localhost). Because you are typically using an HTTP LAN URL
          (e.g. <code>http://&lt;PC-IP&gt;:{backendPort}/app/</code>), Wake Lock may be unavailable; in that
          case EDCA uses a safe fallback that requires a single tap to start.
          <br />
          <strong>Where to tap:</strong> tap anywhere on the EDCA page after enabling this option
          (for example, tap the page background or any button). The header indicator should change
          from “Keep awake: Tap to enable” to “Keep awake: On”.
        </Typography>

        <Divider sx={{ my: 2 }} />

        <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
          Journal Directory
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Path to your Elite: Dangerous journal directory. This is usually found in 'C:\\Users\\%USERNAME%\\Saved Games\\Frontier Developments\\Elite Dangerous'.
        </Typography>
        <TextField
          fullWidth
          label="Journal Directory Path"
          name="journal_directory"
          value={settings.journal_directory}
          onChange={handleChange}
          variant="outlined"
          sx={{ mb: 3 }}
        />

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <Button
            variant="contained"
            color="primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? <CircularProgress size={24} /> : 'Save Settings'}
          </Button>
        </Box>

        <Typography variant="h6" gutterBottom>
          Accessing the UI from another device
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          To open EDCA from a tablet or phone on the same network, point the browser at
          this machine's IP address on port {backendPort}. For example:
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'monospace',
            bgcolor: 'background.default',
            px: 1.5,
            py: 0.75,
            borderRadius: 1,
            mb: 2,
          }}
        >
          {lanUrlHint}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          On this PC you can always use:
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'monospace',
            bgcolor: 'background.default',
            px: 1.5,
            py: 0.75,
            borderRadius: 1,
          }}
        >
          {localUrl}
        </Typography>
      </Box>
    </Paper>
  );
};
