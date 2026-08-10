/**
 * The About tab: build identity plus third-party acknowledgements.
 *
 * Long-form static copy, kept out of App.tsx so the root component is
 * structure rather than prose. The dynamic parts are the versions the
 * backend reports and the manual Check for Updates, which runs the real
 * check (ignoring a skipped version) and reports every outcome: an update
 * opens the prompt from App, the other two outcomes read out here.
 */

import { useState } from 'react';
import { Box, Button, Typography } from '@mui/material';

import type { ManualCheckOutcome } from '../../hooks/useUpdateCheck';

const OUTCOME_MESSAGES: Partial<Record<ManualCheckOutcome, string>> = {
  latest: 'You are running the latest version.',
  unreachable: 'The update check could not reach GitHub. Please try again later.',
};

export interface AboutPanelProps {
  appVersion: string | null;
  pythonVersion: string | null;
  healthError: string | null;
  /** Runs the manual check; an 'update' outcome opens the prompt upstream. */
  onCheckForUpdates: () => Promise<ManualCheckOutcome>;
}

export function AboutPanel({
  appVersion,
  pythonVersion,
  healthError,
  onCheckForUpdates,
}: AboutPanelProps) {
  const [checking, setChecking] = useState(false);
  const [outcome, setOutcome] = useState<ManualCheckOutcome | null>(null);

  const handleCheck = async () => {
    setChecking(true);
    setOutcome(null);
    const result = await onCheckForUpdates();
    setOutcome(result);
    setChecking(false);
  };

  return (
    <Box sx={{ pt: 4, maxWidth: 900 }}>
      <Typography variant="h5" gutterBottom>
        About
      </Typography>
      <Typography variant="body1" sx={{ mb: 2 }}>
        Application Name: EDColonisationAsst
      </Typography>
      <Typography variant="body1" sx={{ mb: 2 }}>
        Author: Oliver Ernster
      </Typography>
      <Typography variant="body1" sx={{ mb: 1.5 }}>
        Version: {appVersion ?? 'Loading...'}
      </Typography>
      <Typography variant="body1" sx={{ mb: 3 }}>
        Python runtime: {pythonVersion ?? 'Loading...'}
      </Typography>
      {healthError && (
        <Typography variant="body2" color="error" sx={{ mt: 1, mb: 2 }}>
          {healthError}
        </Typography>
      )}

      <Box sx={{ mb: 3 }}>
        <Button variant="outlined" size="small" onClick={handleCheck} disabled={checking}>
          Check for Updates
        </Button>
        {outcome && OUTCOME_MESSAGES[outcome] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            {OUTCOME_MESSAGES[outcome]}
          </Typography>
        )}
      </Box>

      <Typography variant="h6" gutterBottom>
        Third&#8209;party components
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        This project makes use of several third&#8209;party libraries. In particular:
      </Typography>

      <Typography variant="subtitle1" sx={{ mt: 1 }}>
        Python backend (key libraries)
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        The backend is built on top of a number of open&#8209;source Python projects, including
        but not limited to:
      </Typography>
      <Typography variant="body2" sx={{ mb: 1, pl: 2 }}>
        &#8226; <strong>FastAPI</strong>: modern, async web framework for the API layer.<br />
        &#8226; <strong>Uvicorn</strong>: ASGI server used to host the FastAPI application.<br />
        &#8226; <strong>Pydantic</strong>: data validation and settings management.<br />
        &#8226; <strong>PySide6</strong>: Qt for Python bindings used for the Windows tray UI
          and installer tooling.<br />
        &#8226; <strong>SQLAlchemy / SQLite</strong> and related tools: persistence layer for
          colonisation data.<br />
        &#8226; Various supporting libraries for logging, testing and utilities as listed in
          <code>backend/requirements.txt</code> and <code>backend/requirements-dev.txt</code>.
      </Typography>
      <Typography variant="body2" sx={{ mb: 2 }}>
        I gratefully acknowledge the maintainers and contributors of these projects and
        the broader Python ecosystem.
      </Typography>

      <Typography variant="subtitle1">Frontend and tooling (Node.js ecosystem)</Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        The React/TypeScript frontend and build tooling rely on many projects from the
        Node.js ecosystem, including:
      </Typography>
      <Typography variant="body2" sx={{ mb: 1, pl: 2 }}>
        &#8226; <strong>React</strong> and <strong>React&#8209;DOM</strong>: core UI framework.<br />
        &#8226; <strong>Material UI (MUI)</strong>: component library for the web UI.<br />
        &#8226; <strong>Vite</strong>: dev server and build tool.<br />
        &#8226; <strong>Zustand</strong>: state management.<br />
        &#8226; <strong>Axios</strong>: HTTP client.<br />
        &#8226; A number of testing, linting and type&#8209;checking tools (Vitest, ESLint,
          TypeScript, Testing Library, etc.) as listed in
          <code>frontend/package.json</code> and <code>frontend/package-lock.json</code>.
      </Typography>
      <Typography variant="body2" sx={{ mb: 2 }}>
        I also gratefully acknowledge the authors and maintainers of these libraries and
        the wider JavaScript/TypeScript ecosystem.
      </Typography>

      <Typography variant="body2">
        Please refer to the upstream project documentation and license notices for each
        of these dependencies for their full terms and acknowledgements.
      </Typography>
    </Box>
  );
}
