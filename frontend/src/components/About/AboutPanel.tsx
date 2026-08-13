/**
 * The About tab: build identity plus third-party acknowledgements.
 *
 * Long-form static copy, kept out of App.tsx so the root component is
 * structure rather than prose. The only dynamic parts are the versions the
 * backend reports.
 *
 * There is deliberately no update check here. This HUD is served over the
 * local network and is meant to be read from a tablet beside the game, so it
 * has no way of knowing whether the device looking at it is the machine EDCA
 * is installed on. Offering a download to a tablet that cannot install
 * anything is the failure that removed it. The tray owns the update check: it
 * runs on the machine that can act on the answer. Having one owner also ends
 * the case where two surfaces raised two prompts for one release, each with a
 * skip the other could not see.
 */

import { Box, Typography } from '@mui/material';

export interface AboutPanelProps {
  appVersion: string | null;
  pythonVersion: string | null;
  healthError: string | null;
}

export function AboutPanel({
  appVersion,
  pythonVersion,
  healthError,
}: AboutPanelProps) {
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
