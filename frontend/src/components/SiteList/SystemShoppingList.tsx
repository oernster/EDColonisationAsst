import { Box, Chip, LinearProgress, Paper, Typography } from '@mui/material';
import { CommodityAggregate } from '../../types/colonisation';

interface SystemShoppingListProps {
  /** Already filtered to commodities with something still outstanding. */
  commodities: CommodityAggregate[];
}

const COMPLETE_PERCENTAGE = 100;

/** The amber used for the inline "Need N more" note, outside the MUI palette. */
const NEEDED_COLOUR = '#FF9800';

const ShoppingListEntry = ({ commodity }: { commodity: CommodityAggregate }) => {
  const isComplete = commodity.progress_percentage >= COMPLETE_PERCENTAGE;

  return (
    <Box
      sx={{
        p: 2,
        mb: 1,
        bgcolor: 'background.default',
        borderRadius: 1,
        borderLeft: 4,
        borderColor: isComplete ? 'success.main' : 'warning.main',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          mb: 1,
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Typography variant="body1" fontWeight="medium">
          {commodity.commodity_name_localised}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Avg payment {Math.round(commodity.average_payment).toLocaleString()} CR/t
        </Typography>
      </Box>

      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          mb: 1,
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          {commodity.total_provided.toLocaleString()} /{' '}
          {commodity.total_required.toLocaleString()} total
          {commodity.total_remaining > 0 && (
            <span style={{ color: NEEDED_COLOUR, marginLeft: 8 }}>
              (Need {commodity.total_remaining.toLocaleString()} more)
            </span>
          )}
        </Typography>
        <Typography variant="body2" fontWeight="bold">
          {commodity.progress_percentage.toFixed(1)}%
        </Typography>
      </Box>

      <LinearProgress
        variant="determinate"
        value={commodity.progress_percentage}
        sx={{
          height: 6,
          borderRadius: 1,
          bgcolor: 'grey.800',
          '& .MuiLinearProgress-bar': {
            bgcolor: isComplete ? 'success.main' : 'warning.main',
          },
        }}
      />

      {commodity.sites_requiring.length > 0 && (
        <Box
          sx={{
            mt: 1,
            display: 'flex',
            flexWrap: 'wrap',
            gap: 0.5,
            alignItems: 'center',
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
            Needed at:
          </Typography>
          {commodity.sites_requiring.map((station) => (
            <Chip key={station} label={station} size="small" variant="outlined" />
          ))}
        </Box>
      )}
    </Box>
  );
};

/**
 * Everything the system still needs, in one list.
 *
 * The empty case is worth its own words: an empty list here usually means the
 * sites have not advertised requirements yet, not that the work is done.
 */
export const SystemShoppingList = ({ commodities }: SystemShoppingListProps) => {
  return (
    <Paper sx={{ p: 3, mb: 3, bgcolor: 'background.paper' }}>
      <Typography variant="h6" gutterBottom>
        System Shopping List
      </Typography>

      {commodities.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No commodity requirements are currently available for this system.
          Once construction sites advertise required commodities in the
          journals or via Inara, they will appear here.
        </Typography>
      ) : (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Aggregated commodities still needed across all construction sites
            in this system.
          </Typography>
          {commodities.map((commodity) => (
            <ShoppingListEntry key={commodity.commodity_name} commodity={commodity} />
          ))}
        </>
      )}
    </Paper>
  );
};
