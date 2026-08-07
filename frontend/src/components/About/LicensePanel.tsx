/**
 * The License tab.
 *
 * Static copy naming the licence and pointing at the authoritative text, which
 * ships with the installed application as well as living in the repository.
 */

import { Box, Link, Typography } from '@mui/material';

const LICENCE_URL = 'https://github.com/oernster/EDColonisationAsst/blob/main/LICENSE';

export function LicensePanel() {
  return (
    <Box sx={{ pt: 4, maxWidth: 900 }}>
      <Typography variant="h5" gutterBottom>
        License
      </Typography>
      <Typography variant="body1" sx={{ mb: 2 }}>
        Elite Dangerous Colonisation Assistant (EDCA) is distributed under the terms of
        the <strong>GNU Lesser General Public License, version 3</strong> (LGPL&#8209;3.0).
      </Typography>
      <Typography variant="body2" sx={{ mb: 2 }}>
        The full text of the license is available online at{' '}
        <Link href={LICENCE_URL} target="_blank" rel="noopener noreferrer">
          LICENSE
        </Link>{' '}
        and is also included in the installed application as the file
        <code> LICENSE</code>. By using this software you agree to the terms of that license.
      </Typography>
    </Box>
  );
}
