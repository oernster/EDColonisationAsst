/**
 * Version, runtime and commander details read from the backend.
 *
 * Re-read whenever the settings version changes, because the commander name
 * lives in settings. The two requests fail independently: a health failure is
 * surfaced to the user, whereas a missing commander name is simply blank.
 */

import { useEffect, useState } from 'react';

import { api } from '../services/api';

export interface BackendMeta {
  appVersion: string | null;
  pythonVersion: string | null;
  healthError: string | null;
  commanderName: string | null;
}

export function useBackendMeta(settingsVersion: number): BackendMeta {
  const [appVersion, setAppVersion] = useState<string | null>(null);
  const [pythonVersion, setPythonVersion] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [commanderName, setCommanderName] = useState<string | null>(null);

  useEffect(() => {
    const loadMeta = async () => {
      try {
        const health = await api.healthCheck();
        setAppVersion(
          health.build_id ? `${health.version} (${health.build_id})` : health.version,
        );
        // Surface the actual Python runtime version reported by the backend, so
        // the embedded interpreter the packaged EXE uses is visible at a glance.
        setPythonVersion(health.python_version ?? null);
      } catch {
        setHealthError('Failed to load version information');
      }

      try {
        const settings = await api.getAppSettings();
        setCommanderName(settings.inara_commander_name);
      } catch {
        // Ignore settings load errors here; commander name is optional display.
      }
    };

    loadMeta();
  }, [settingsVersion]);

  return { appVersion, pythonVersion, healthError, commanderName };
}
