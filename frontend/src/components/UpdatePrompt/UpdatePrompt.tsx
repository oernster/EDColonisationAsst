/**
 * The update prompt: Download, Skip this version or Later.
 *
 * Download opens the Windows installer asset directly, falling back to the
 * releases page when the release carries none; run it over the existing
 * installation to upgrade. Skip persists the offered version in this
 * browser so it never prompts again; Later simply closes the prompt while
 * the header control remains as the way back in.
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
  onSkip: () => void;
  onLater: () => void;
}

export function UpdatePrompt({
  open,
  latestVersion,
  currentVersion,
  downloadUrl,
  pageUrl,
  onSkip,
  onLater,
}: UpdatePromptProps) {
  return (
    <Dialog open={open} onClose={onLater} aria-labelledby="update-prompt-title">
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
          onClick={onLater}
        >
          Download
        </Button>
        <Button color="warning" onClick={onSkip}>
          Skip this version
        </Button>
        <Button onClick={onLater}>Later</Button>
      </DialogActions>
    </Dialog>
  );
}
