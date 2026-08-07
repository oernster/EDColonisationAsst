/**
 * The two MUI themes the application switches between.
 *
 * Kept out of App.tsx because a theme definition is configuration rather than
 * component logic; also because both themes share a typography stack that is
 * easier to keep identical when they sit side by side.
 */

import { createTheme } from '@mui/material';

const FONT_FAMILY =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif';

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#FF6B00', // Elite orange
    },
    secondary: {
      main: '#4CAF50', // Green for completed
    },
    background: {
      default: '#1a1a1a',
      paper: '#2d2d2d',
    },
    success: {
      main: '#4CAF50', // Green
    },
    warning: {
      main: '#FF9800', // Orange
    },
  },
  typography: {
    fontFamily: FONT_FAMILY,
  },
});

export const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#FF6B00', // Elite orange
    },
    secondary: {
      main: '#2e7d32', // Darker green
    },
    background: {
      default: '#fafafa',
      paper: '#ffffff',
    },
    success: {
      main: '#2e7d32',
    },
    warning: {
      main: '#FF9800',
    },
  },
  typography: {
    fontFamily: FONT_FAMILY,
  },
});
