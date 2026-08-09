/**
 * Version, runtime and commander details read from the backend.
 *
 * The commander details (name, credit balance, docked context) are detected
 * from the journals via the journal status endpoint, so nothing needs
 * entering in Settings. They are re-read on a timer because they change as
 * the commander plays, and whenever the settings version changes, because a
 * changed journal directory changes which journals they come from. The two
 * requests fail independently: a health failure is surfaced to the user,
 * whereas missing commander details are simply blank.
 */

import { useEffect, useState } from 'react';

import { api } from '../services/api';
import { CurrentSystem } from '../types/colonisation';

// The commander details cost one parse of the newest journal file per read,
// so they are refreshed on a gentle timer rather than per keystroke of play.
const COMMANDER_REFRESH_MS = 30_000;

export interface BackendMeta {
  appVersion: string | null;
  /** The bare x.y.z, without the build marker; what the update check compares. */
  appVersionRaw: string | null;
  pythonVersion: string | null;
  healthError: string | null;
  commanderStatus: CurrentSystem | null;
}

export function useBackendMeta(settingsVersion: number): BackendMeta {
  const [appVersion, setAppVersion] = useState<string | null>(null);
  const [appVersionRaw, setAppVersionRaw] = useState<string | null>(null);
  const [pythonVersion, setPythonVersion] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [commanderStatus, setCommanderStatus] = useState<CurrentSystem | null>(null);

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const health = await api.healthCheck();
        setAppVersion(
          health.build_id ? `${health.version} (${health.build_id})` : health.version,
        );
        setAppVersionRaw(health.version ?? null);
        // Surface the actual Python runtime version reported by the backend, so
        // the embedded interpreter the packaged EXE uses is visible at a glance.
        setPythonVersion(health.python_version ?? null);
      } catch {
        setHealthError('Failed to load version information');
      }
    };

    const loadCommander = async () => {
      try {
        setCommanderStatus(await api.getCurrentSystem());
      } catch {
        // Ignore journal status errors here; commander details are optional
        // display.
      }
    };

    loadHealth();
    loadCommander();
    const timer = window.setInterval(loadCommander, COMMANDER_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [settingsVersion]);

  return { appVersion, appVersionRaw, pythonVersion, healthError, commanderStatus };
}
