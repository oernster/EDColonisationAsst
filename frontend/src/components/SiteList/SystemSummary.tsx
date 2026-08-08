import { Box, Collapse, Grid, IconButton, Paper, Typography } from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';
import { SystemColonisationData } from '../../types/colonisation';

interface SystemSummaryProps {
  systemData: SystemColonisationData;
  expanded: boolean;
  onToggle: () => void;
}

/**
 * The four counts at the top of the system view.
 *
 * The collapse state is owned by SiteList rather than here, because the
 * shopping list below collapses with it and the two have to agree.
 */
export const SystemSummary = ({
  systemData,
  expanded,
  onToggle,
}: SystemSummaryProps) => {
  return (
    <Paper sx={{ p: 3, mb: 2, bgcolor: 'background.paper' }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: expanded ? 2 : 0,
        }}
      >
        <Typography variant="h5">
          {systemData.system_name}
        </Typography>
        <IconButton
          size="small"
          onClick={onToggle}
          aria-label={expanded ? 'Collapse system details' : 'Expand system details'}
        >
          {expanded ? <ExpandLess /> : <ExpandMore />}
        </IconButton>
      </Box>

      <Collapse in={expanded} timeout="auto" unmountOnExit>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <Typography variant="body2" color="text.secondary">
              Total Sites
            </Typography>
            <Typography variant="h6">{systemData.total_sites}</Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Typography variant="body2" color="text.secondary">
              Completed
            </Typography>
            <Typography variant="h6" color="success.main">
              {systemData.completed_sites}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Typography variant="body2" color="text.secondary">
              In Progress
            </Typography>
            <Typography variant="h6" color="warning.main">
              {systemData.in_progress_sites}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Typography variant="body2" color="text.secondary">
              Overall Progress
            </Typography>
            <Typography variant="h6">
              {systemData.completion_percentage.toFixed(1)}%
            </Typography>
          </Grid>
        </Grid>
      </Collapse>
    </Paper>
  );
};
