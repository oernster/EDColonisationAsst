import { useEffect, useMemo, useState } from 'react';
import { Box, Typography, Paper, LinearProgress, Chip, Grid, Collapse, IconButton, Tabs, Tab } from '@mui/material';
import { CheckCircle, Construction, ExpandLess, ExpandMore } from '@mui/icons-material';
import { useColonisationStore } from '../../stores/colonisationStore';
import { ConstructionSite, CommodityStatus, CommodityAggregate } from '../../types/colonisation';

type SiteListViewMode = 'system' | 'stations' | 'completed_stations';

const aggregateCommodities = (
  sites: ConstructionSite[]
): CommodityAggregate[] => {
  const commodityMap: {
    [name: string]: {
      name: string;
      name_localised: string;
      total_required: number;
      total_provided: number;
      sites: Set<string>;
      payments: number[];
    };
  } = {};

  sites.forEach((site) => {
    site.commodities.forEach((commodity) => {
      const key = commodity.name;

      if (!commodityMap[key]) {
        commodityMap[key] = {
          name: commodity.name,
          name_localised: commodity.name_localised,
          total_required: 0,
          total_provided: 0,
          sites: new Set<string>(),
          payments: [],
        };
      }

      const entry = commodityMap[key];

      entry.total_required += commodity.required_amount;
      entry.total_provided += commodity.provided_amount;

      if (commodity.remaining_amount > 0) {
        entry.sites.add(site.station_name);
      }

      entry.payments.push(commodity.payment);
    });
  });

  const aggregates: CommodityAggregate[] = Object.values(commodityMap).map(
    (data) => {
      const average_payment =
        data.payments.length > 0
          ? data.payments.reduce((sum, value) => sum + value, 0) /
            data.payments.length
          : 0;

      const total_remaining = Math.max(
        0,
        data.total_required - data.total_provided
      );

      const progress_percentage =
        data.total_required === 0
          ? 100
          : (data.total_provided / data.total_required) * 100;

      return {
        commodity_name: data.name,
        commodity_name_localised: data.name_localised,
        total_required: data.total_required,
        total_provided: data.total_provided,
        sites_requiring: Array.from(data.sites),
        average_payment,
        total_remaining,
        progress_percentage,
      };
    }
  );

  aggregates.sort((a, b) => b.total_remaining - a.total_remaining);

  return aggregates;
};

export const SiteList = ({ viewMode = 'system' }: { viewMode?: SiteListViewMode }) => {
  const { systemData } = useColonisationStore();
  const [systemExpanded, setSystemExpanded] = useState(true);
  const [stationTab, setStationTab] = useState(0);

  // NOTE: user-requested rule: station is completed iff ALL of these are true.
  // Backend currently sets is_complete := construction_complete; we still honor both fields.
  const isStationCompleted = (site: ConstructionSite): boolean => {
    const hasAllCommoditiesDelivered =
      site.commodities.length === 0 ||
      site.commodities.every(
        (c) => c.remaining_amount === 0 || c.status === CommodityStatus.COMPLETED
      );

    return Boolean(site.construction_complete) && Boolean(site.is_complete) && hasAllCommoditiesDelivered;
  };

  const filteredConstructionSites = useMemo(() => {
    if (!systemData) return [] as ConstructionSite[];

    if (viewMode === 'stations') {
      return systemData.construction_sites.filter((s) => !isStationCompleted(s));
    }

    // New mode: show only completed stations.
    if (viewMode === 'completed_stations') {
      return systemData.construction_sites.filter((s) => isStationCompleted(s));
    }

    return systemData.construction_sites;
  }, [systemData, viewMode]);

  // If the filtered list shrinks, keep stationTab in range.
  useEffect(() => {
    if (stationTab >= filteredConstructionSites.length) {
      setStationTab(0);
    }
  }, [filteredConstructionSites.length, stationTab]);

  if (!systemData || systemData.construction_sites.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <Typography color="text.secondary">
          No construction sites found in this system
        </Typography>
      </Box>
    );
  }

  if (viewMode === 'stations' && filteredConstructionSites.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <Typography color="text.secondary">
          No in-progress stations found in this system
        </Typography>
      </Box>
    );
  }

  if (viewMode === 'completed_stations' && filteredConstructionSites.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <Typography color="text.secondary">
          No completed stations found in this system
        </Typography>
      </Box>
    );
  }

  const shoppingList = aggregateCommodities(
    systemData.construction_sites
  ).filter((item) => item.total_remaining > 0);

  return (
    <Box>
      {/* System Summary */}
      <Paper sx={{ p: 3, mb: 2, bgcolor: 'background.paper' }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            mb: systemExpanded ? 2 : 0,
          }}
        >
          <Typography variant="h5">
            {systemData.system_name}
          </Typography>
          <IconButton
            size="small"
            onClick={() => setSystemExpanded((prev) => !prev)}
            aria-label={systemExpanded ? 'Collapse system details' : 'Expand system details'}
          >
            {systemExpanded ? <ExpandLess /> : <ExpandMore />}
          </IconButton>
        </Box>

        <Collapse in={systemExpanded} timeout="auto" unmountOnExit>
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

      {/* System Shopping List (tab-controlled) */}
      {viewMode === 'system' && (
        <Collapse in={systemExpanded} timeout="auto" unmountOnExit>
          <Paper sx={{ p: 3, mb: 3, bgcolor: 'background.paper' }}>
            <Typography variant="h6" gutterBottom>
              System Shopping List
            </Typography>

            {shoppingList.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No commodity requirements are currently available for this system.
                Once construction sites advertise required commodities in the
                journals or via Inara, they will appear here.
              </Typography>
            ) : (
              <>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 2 }}
                >
                  Aggregated commodities still needed across all construction sites
                  in this system.
                </Typography>
                {shoppingList.map((commodity) => (
                  <Box
                    key={commodity.commodity_name}
                    sx={{
                      p: 2,
                      mb: 1,
                      bgcolor: 'background.default',
                      borderRadius: 1,
                      borderLeft: 4,
                      borderColor:
                        commodity.progress_percentage >= 100
                          ? 'success.main'
                          : 'warning.main',
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
                        Avg payment{' '}
                        {Math.round(
                          commodity.average_payment
                        ).toLocaleString()}{' '}
                        CR/t
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
                          <span style={{ color: '#FF9800', marginLeft: 8 }}>
                            (Need{' '}
                            {commodity.total_remaining.toLocaleString()} more)
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
                            commodity.progress_percentage >= 100
                              ? 'success.main'
                              : 'warning.main',
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
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ mr: 1 }}
                        >
                          Needed at:
                        </Typography>
                        {commodity.sites_requiring.map((station) => (
                          <Chip
                            key={station}
                            label={station}
                            size="small"
                            variant="outlined"
                          />
                        ))}
                      </Box>
                    )}
                  </Box>
                ))}
              </>
            )}
          </Paper>
        </Collapse>
      )}

      {/* Construction Sites (tab-controlled) */}
      {(viewMode === 'stations' || viewMode === 'completed_stations') && (
        <>
          <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
            <Tabs
              value={stationTab}
              onChange={(_, newValue: number) => setStationTab(newValue)}
              aria-label="station tabs"
              variant="scrollable"
              scrollButtons="auto"
            >
              {filteredConstructionSites.map((site, index) => (
                <Tab
                  key={site.market_id}
                  label={site.station_name}
                  id={`station-tab-${index}`}
                  aria-controls={`station-tabpanel-${index}`}
                />
              ))}
            </Tabs>
          </Box>

          {filteredConstructionSites.length > 0 && (
            <SiteCard
              key={
                filteredConstructionSites[
                  stationTab < filteredConstructionSites.length ? stationTab : 0
                ].market_id
              }
              site={
                filteredConstructionSites[
                  stationTab < filteredConstructionSites.length ? stationTab : 0
                ]
              }
            />
          )}
        </>
      )}
    </Box>
  );
};

const SiteCard = ({ site }: { site: ConstructionSite }) => {
  const isComplete = site.construction_complete;

  // Live per-site progress is derived from *commodity delivery totals*.
  // This is more responsive than the journal's ConstructionProgress field,
  // which can remain static for long periods.
  const { totalRequired, totalProvided, deliveryProgressPercentage, hasRequirements } = useMemo(() => {
    const commodities = site.commodities ?? [];
    const totalRequired = commodities.reduce((sum, c) => sum + (c.required_amount ?? 0), 0);
    const totalProvided = commodities.reduce((sum, c) => sum + (c.provided_amount ?? 0), 0);

    // If we have no commodity requirements at all, we cannot compute a meaningful
    // delivery percentage yet.
    const hasRequirements = commodities.length > 0 && totalRequired > 0;

    const deliveryProgressPercentage = hasRequirements
      ? (totalProvided / totalRequired) * 100
      : null;

    return {
      totalRequired,
      totalProvided,
      deliveryProgressPercentage,
      hasRequirements,
    };
  }, [site.commodities]);

  const displayedConstructionProgress = isComplete
    ? 100
    : deliveryProgressPercentage === null
      ? null
      : Math.max(0, Math.min(100, deliveryProgressPercentage));
  const statusColor = isComplete ? 'success.main' : 'info.main';
  const statusIcon = isComplete ? <CheckCircle /> : <Construction />;
  const [expanded, setExpanded] = useState(true);

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
            {displayedConstructionProgress === null ? (
              <Typography variant="body2" color="text.secondary">
                Awaiting requirements
              </Typography>
            ) : (
              <Typography
                variant="body2"
                fontWeight="bold"
                data-testid={`site-progress-label-${site.market_id}`}
              >
                {displayedConstructionProgress.toFixed(1)}%
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
            variant={displayedConstructionProgress === null ? 'indeterminate' : 'determinate'}
            value={displayedConstructionProgress === null ? 0 : displayedConstructionProgress}
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
              <Box
                key={index}
                sx={{
                  p: 2,
                  mb: 1,
                  bgcolor: 'background.default',
                  borderRadius: 1,
                  borderLeft: 4,
                  borderColor:
                    commodity.status === CommodityStatus.COMPLETED
                      ? 'success.main'
                      : commodity.status === CommodityStatus.IN_PROGRESS
                      ? 'warning.main'
                      : 'grey.700',
                }}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography
                    variant="body1"
                    fontWeight="medium"
                    sx={{
                      color:
                        commodity.status === CommodityStatus.COMPLETED
                          ? 'success.main'
                          : commodity.status === CommodityStatus.IN_PROGRESS
                          ? 'warning.main'
                          : 'text.primary',
                    }}
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
                      <span style={{ color: '#FF9800', marginLeft: 8 }}>
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
