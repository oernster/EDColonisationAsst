import { useMemo, useState } from 'react';
import { Box, Chip, Collapse, IconButton, LinearProgress, Paper, Typography } from '@mui/material';
import { CheckCircle, Construction, ExpandLess, ExpandMore } from '@mui/icons-material';
import { Commodity, CommodityStatus, ConstructionSite } from '../../types/colonisation';
import { displayedProgress, siteDeliveryProgress } from './siteAggregation';

/** The amber used for the inline "Need N more" note, outside the MUI palette. */
const NEEDED_COLOUR = '#FF9800';

const commodityColour = (status: CommodityStatus, pending: string) => {
  if (status === CommodityStatus.COMPLETED) {
    return 'success.main';
  }
  if (status === CommodityStatus.IN_PROGRESS) {
    return 'warning.main';
  }
  return pending;
};

const CommodityRow = ({ commodity }: { commodity: Commodity }) => {
  return (
    <Box
      sx={{
        p: 2,
        mb: 1,
        bgcolor: 'background.default',
        borderRadius: 1,
        borderLeft: 4,
        borderColor: commodityColour(commodity.status, 'grey.700'),
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
        <Typography
          variant="body1"
          fontWeight="medium"
          sx={{ color: commodityColour(commodity.status, 'text.primary') }}
        >
          {commodity.status === CommodityStatus.COMPLETED && '✓ '}
          {commodity.name_localised}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Payment: {commodity.payment.toLocaleString()} CR
        </Typography>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="body2" color="text.secondary">
          {commodity.provided_amount.toLocaleString()} /{' '}
          {commodity.required_amount.toLocaleString()}
          {commodity.remaining_amount > 0 && (
            <span style={{ color: NEEDED_COLOUR, marginLeft: 8 }}>
              (Need {commodity.remaining_amount.toLocaleString()} more)
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
            bgcolor:
              commodity.status === CommodityStatus.COMPLETED
                ? 'success.main'
                : 'warning.main',
          },
        }}
      />
    </Box>
  );
};

/**
 * One construction site, with its delivery progress and what it still wants.
 *
 * The percentage shown is derived from commodity totals rather than from the
 * journal's ConstructionProgress field; see siteAggregation for why.
 */
export const SiteCard = ({ site }: { site: ConstructionSite }) => {
  const isComplete = site.construction_complete;
  const [expanded, setExpanded] = useState(true);

  const { totalRequired, totalProvided, deliveryProgressPercentage, hasRequirements } =
    useMemo(() => siteDeliveryProgress(site), [site]);

  const progress = displayedProgress(isComplete, deliveryProgressPercentage);
  const statusColor = isComplete ? 'success.main' : 'info.main';
  const statusIcon = isComplete ? <CheckCircle /> : <Construction />;

  return (
    <Paper sx={{ p: 3, mb: 2, bgcolor: 'background.paper' }}>
      {/* Site Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expanded ? 2 : 0 }}>
        <Box sx={{ color: statusColor }}>{statusIcon}</Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6">{site.station_name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {site.station_type}
          </Typography>
        </Box>
        <Chip
          label={isComplete ? 'COMPLETE' : 'IN PROGRESS'}
          color={isComplete ? 'success' : 'info'}
          size="small"
        />
        <Chip
          label={`Source: ${site.last_source || 'journal'}`}
          size="small"
          variant="outlined"
          sx={{ ml: 1 }}
        />
        <IconButton
          size="small"
          onClick={() => setExpanded((prev) => !prev)}
          aria-label={expanded ? 'Collapse site' : 'Expand site'}
          sx={{ ml: 1 }}
        >
          {expanded ? <ExpandLess /> : <ExpandMore />}
        </IconButton>
      </Box>

      <Collapse in={expanded} timeout="auto" unmountOnExit>
        {/* Progress Bar */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Commodities Delivered
            </Typography>
            {progress === null ? (
              <Typography variant="body2" color="text.secondary">
                Awaiting requirements
              </Typography>
            ) : (
              <Typography
                variant="body2"
                fontWeight="bold"
                data-testid={`site-progress-label-${site.market_id}`}
              >
                {progress.toFixed(1)}%
              </Typography>
            )}
          </Box>

          {hasRequirements && !isComplete && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              {totalProvided.toLocaleString()} / {totalRequired.toLocaleString()} delivered
            </Typography>
          )}

          <LinearProgress
            data-testid={`site-progress-${site.market_id}`}
            variant={progress === null ? 'indeterminate' : 'determinate'}
            value={progress === null ? 0 : progress}
            sx={{
              height: 8,
              borderRadius: 1,
              bgcolor: 'grey.800',
              '& .MuiLinearProgress-bar': {
                bgcolor: isComplete ? 'success.main' : 'info.main',
              },
            }}
          />
        </Box>

        {/* Commodities */}
        {site.commodities.length > 0 && (
          <Box>
            <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
              Commodities Required:
            </Typography>
            {site.commodities.map((commodity, index) => (
              <CommodityRow key={index} commodity={commodity} />
            ))}
          </Box>
        )}

        {isComplete && (
          <Box sx={{ mt: 2, p: 2, bgcolor: 'success.dark', borderRadius: 1 }}>
            <Typography color="success.contrastText" textAlign="center">
              ✓ All commodities delivered - Construction complete!
            </Typography>
          </Box>
        )}
      </Collapse>
    </Paper>
  );
};
