import { useEffect, useMemo, useState } from 'react';
import { Box, Collapse, Tabs, Tab, Typography } from '@mui/material';
import { useColonisationStore } from '../../stores/colonisationStore';
import { ConstructionSite } from '../../types/colonisation';
import { SiteCard } from './SiteCard';
import { SystemShoppingList } from './SystemShoppingList';
import { SystemSummary } from './SystemSummary';
import { aggregateCommodities, isStationCompleted } from './siteAggregation';

export type SiteListViewMode = 'system' | 'stations' | 'completed_stations';

/** What to say when a view has nothing to show, keyed by that view. */
const EMPTY_MESSAGES: Record<SiteListViewMode, string> = {
  system: 'No construction sites found in this system',
  stations: 'No in-progress stations found in this system',
  completed_stations: 'No completed stations found in this system',
};

const EmptyMessage = ({ children }: { children: string }) => (
  <Box sx={{ textAlign: 'center', py: 4 }}>
    <Typography color="text.secondary">{children}</Typography>
  </Box>
);

/**
 * The system view: a summary, what the system still needs and a tab per site.
 *
 * Which sections appear is decided entirely by `viewMode`, which App.tsx maps
 * from its own sub-tabs. The sections themselves live beside this file; what
 * is here is the filtering, the empty states and which site the tabs select.
 */
export const SiteList = ({ viewMode = 'system' }: { viewMode?: SiteListViewMode }) => {
  const { systemData } = useColonisationStore();
  const [systemExpanded, setSystemExpanded] = useState(true);
  const [stationTab, setStationTab] = useState(0);

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
    return <EmptyMessage>{EMPTY_MESSAGES.system}</EmptyMessage>;
  }

  if (viewMode !== 'system' && filteredConstructionSites.length === 0) {
    return <EmptyMessage>{EMPTY_MESSAGES[viewMode]}</EmptyMessage>;
  }

  const shoppingList = aggregateCommodities(systemData.construction_sites).filter(
    (item) => item.total_remaining > 0,
  );

  // Guard the index rather than trusting it. The effect above resets it,
  // yet that runs only after this render.
  const selectedSite =
    filteredConstructionSites[
      stationTab < filteredConstructionSites.length ? stationTab : 0
    ];

  return (
    <Box>
      <SystemSummary
        systemData={systemData}
        expanded={systemExpanded}
        onToggle={() => setSystemExpanded((prev) => !prev)}
      />

      {viewMode === 'system' && (
        <Collapse in={systemExpanded} timeout="auto" unmountOnExit>
          <SystemShoppingList commodities={shoppingList} />
        </Collapse>
      )}

      {viewMode !== 'system' && (
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

          {selectedSite && <SiteCard key={selectedSite.market_id} site={selectedSite} />}
        </>
      )}
    </Box>
  );
};
