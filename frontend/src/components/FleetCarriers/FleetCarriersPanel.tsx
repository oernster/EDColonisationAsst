import { useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  CircularProgress,
  Alert,
} from '@mui/material';
import { useCarrierStore } from '../../stores/carrierStore';
import { CarrierIdentity } from '../../types/fleetCarriers';
import { CarrierCargoSection } from './CarrierCargoSection';
import { CarrierIdentityList } from './CarrierIdentityList';
import { CarrierMarketSection } from './CarrierMarketSection';
import { CurrentCarrierHeader } from './CurrentCarrierHeader';

/**
 * How often the docked carrier snapshot is refetched.
 *
 * Market and cargo changes are written to the journal by the game; the
 * commander can also change them from inside the carrier menu without any
 * event this application would see, so this poll is what keeps the numbers
 * honest while docked. It stops the moment you undock.
 */
const DOCKED_POLL_INTERVAL_MS = 5000;

/** Tab index 0 is the left-most tab: Market on the left, Cargo on the right. */
const MARKET_TAB_INDEX = 0;

const a11yProps = (index: number) => ({
  id: `carrier-tab-${index}`,
  'aria-controls': `carrier-tabpanel-${index}`,
});

/**
 * The Fleet carriers tab.
 *
 * This component owns the data wiring and the layout; each section it shows
 * lives beside it in this directory. Three effects feed it: a load on mount,
 * a listener for the backend change events the long-poll in App.tsx raises,
 * and the docked-only poll above.
 */
export const FleetCarriersPanel = () => {
  const {
    currentCarrierInfo,
    currentCarrierState,
    currentCarrierLoading,
    currentCarrierError,
    myCarriers,
    myCarriersLoading,
    myCarriersError,
    loadCurrentCarrier,
    refreshCurrentCarrier,
    loadMyCarriers,
    carrierViewTab,
    setCarrierViewTab,
  } = useCarrierStore();

  useEffect(() => {
    // Load both the current docked carrier (if any) and the "my carriers" list
    // when the Fleet carriers tab first mounts.
    void loadCurrentCarrier();
    void loadMyCarriers();
  }, [loadCurrentCarrier, loadMyCarriers]);

  // Respond immediately to backend ingestion changes (AJAX long-poll in App.tsx
  // updates system data; carriers are separate endpoints).
  useEffect(() => {
    const onBackendChanged = () => {
      void refreshCurrentCarrier();
      void loadMyCarriers();
    };
    window.addEventListener('edcaBackendChanged', onBackendChanged);
    return () => window.removeEventListener('edcaBackendChanged', onBackendChanged);
  }, [refreshCurrentCarrier, loadMyCarriers]);

  const handleCarrierViewTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setCarrierViewTab(newValue === MARKET_TAB_INDEX ? 'market' : 'cargo');
  };

  const dockedIdentity: CarrierIdentity | null =
    currentCarrierInfo && currentCarrierInfo.docked_at_carrier
      ? currentCarrierInfo.carrier
      : null;

  useEffect(() => {
    // Only poll while we are actually docked at a carrier.
    if (!dockedIdentity) {
      return;
    }

    const id = window.setInterval(() => {
      // Use the background refresh variant so we don't toggle loading state or
      // clear the visible UI, avoiding header "jiggle".
      void refreshCurrentCarrier();
    }, DOCKED_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(id);
    };
  }, [dockedIdentity, refreshCurrentCarrier]);

  const hasNoKnownCarriers =
    !myCarriers ||
    (myCarriers.own_carriers.length === 0 && myCarriers.squadron_carriers.length === 0);

  return (
    <Box>
      {/* Errors */}
      {(currentCarrierError || myCarriersError) && (
        <Box sx={{ mb: 2 }}>
          <Alert severity="error">
            {currentCarrierError || myCarriersError || 'An error occurred loading carrier data.'}
          </Alert>
        </Box>
      )}

      {/* Current docked carrier section */}
      <Paper sx={{ p: 3, mb: 3, bgcolor: 'background.paper' }}>
        <CurrentCarrierHeader
          dockedIdentity={dockedIdentity}
          carrierState={currentCarrierState}
          loading={currentCarrierLoading}
        />

        {dockedIdentity && currentCarrierState && (
          <>
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
              <Tabs
                value={carrierViewTab === 'market' ? 0 : 1}
                onChange={handleCarrierViewTabChange}
                aria-label="carrier detail tabs"
                textColor="primary"
                indicatorColor="primary"
              >
                <Tab label="Market" {...a11yProps(0)} />
                <Tab label="Cargo" {...a11yProps(1)} />
              </Tabs>
            </Box>

            {carrierViewTab === 'cargo' && (
              <CarrierCargoSection
                cargo={currentCarrierState.cargo}
                totalCargoTonnage={currentCarrierState.total_cargo_tonnage ?? null}
                totalCapacityTonnage={currentCarrierState.total_capacity_tonnage ?? null}
                freeSpaceTonnage={currentCarrierState.free_space_tonnage ?? null}
                spaceUsage={currentCarrierState.space_usage ?? null}
                snapshotTime={currentCarrierState.snapshot_time}
                holdSnapshotTime={currentCarrierState.cargo_snapshot_time ?? null}
                unaccountedTonnage={currentCarrierState.cargo_unaccounted_tonnage ?? null}
                buyOrders={currentCarrierState.buy_orders}
              />
            )}
            {carrierViewTab === 'market' && (
              <CarrierMarketSection
                buyOrders={currentCarrierState.buy_orders}
                sellOrders={currentCarrierState.sell_orders}
              />
            )}
          </>
        )}
      </Paper>

      {/* My carriers section (own + squadron) */}
      <Paper sx={{ p: 3, bgcolor: 'background.paper' }}>
        <Typography variant="h6" gutterBottom>
          My carriers
        </Typography>

        {myCarriersLoading && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Loading list of known carriers...
            </Typography>
          </Box>
        )}

        {!myCarriersLoading && hasNoKnownCarriers && (
          <Typography variant="body2" color="text.secondary">
            No own or squadron carriers were found in recent journal events. Once CarrierStats events
            appear in your journals, they will be listed here.
          </Typography>
        )}

        {!myCarriersLoading && myCarriers && (
          <Box sx={{ mt: 2 }}>
            {myCarriers.own_carriers.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <CarrierIdentityList
                  carriers={myCarriers.own_carriers}
                  dockedCarrierId={dockedIdentity?.carrier_id ?? null}
                  dockedCarrierServices={dockedIdentity?.services ?? null}
                />
              </Box>
            )}

            {myCarriers.squadron_carriers.length > 0 && (
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Squadron carriers
                </Typography>
                <CarrierIdentityList
                  carriers={myCarriers.squadron_carriers}
                  dockedCarrierId={dockedIdentity?.carrier_id ?? null}
                  dockedCarrierServices={dockedIdentity?.services ?? null}
                />
              </Box>
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
};
