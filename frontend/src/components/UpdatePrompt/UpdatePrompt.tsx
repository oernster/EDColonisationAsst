/**
 * The update prompt: Download or Close.
 *
 * Download opens the Windows installer asset directly, falling back to the
 * releases page when the release carries none; run it over the existing
 * installation to upgrade.
 *
 * There is no "Skip this version" here. Skipping exists to silence a check
 * that speaks unbidden, and this HUD no longer has one: the single automatic
 * check lives in the tray, which is also where its skip is remembered. A skip
 * button here would write a preference nothing would ever read.
 */

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';

export interface UpdatePromptProps {
  open: boolean;
  latestVersion: string;
  currentVersion: string;
  downloadUrl: string | null;
  pageUrl: string;
  onClose: () => void;
}

export function UpdatePrompt({
  open,
  latestVersion,
  currentVersion,
  downloadUrl,
  pageUrl,
  onClose,
}: UpdatePromptProps) {
  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="update-prompt-title">
      <DialogTitle id="update-prompt-title">Update available</DialogTitle>
      <DialogContent>
        <DialogContentText>
          EDColonisationAsst {latestVersion} is available. You are running{' '}
          {currentVersion}. Download the installer and run it over this
          installation to upgrade.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button
          variant="contained"
          href={downloadUrl ?? pageUrl}
          target="_blank"
          rel="noopener"
          onClick={onClose}
        >
          Download
        </Button>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
