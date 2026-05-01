import { useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Alert,
} from '@mui/material';
import { useCarrierStore } from '../../stores/carrierStore';
import {
  CarrierIdentity,
  CarrierOrder,
  CarrierCargoItem,
} from '../../types/fleetCarriers';

const formatDockingAccess = (access: string) => {
  const normalized = access.toLowerCase();
  switch (normalized) {
    case 'owner':
      return 'Owner only';
    case 'squadron':
      return 'Squadron only';
    case 'friends':
      return 'Friends & squadron';
    case 'all':
      return 'All pilots';
    default:
      return access.charAt(0).toUpperCase() + access.slice(1);
  }
};

/**
 * Normalise a raw journal/service name into a compact key we can use for
 * matching overrides and filters.
 */
const normalizeServiceKey = (service: string): string =>
  service.toLowerCase().replace(/\s+/g, '').replace(/[_-]/g, '');

/**
 * Services that are either commander-specific or effectively always-present
 * and therefore not useful to show in the UI.
 */
const HIDDEN_SERVICE_KEYS = new Set<string>([
  'flightcontroller',
  'socialspace',
  'engineer',
  'stationmenu',
  'stationoperations',
]);

/**
 * Human-friendly label overrides for specific carrier services.
 *
 * These keep each logical service as a single item, but add spaces to make
 * them readable.
 */
const SERVICE_LABEL_OVERRIDES: Record<string, string> = {
  autodock: 'Auto dock',
  carrierfuel: 'Carrier fuel',
  carriermanagement: 'Carrier management',
  crewlounge: 'Crew lounge',
  exploration: 'Cartographics',
  pioneersupplies: 'Pioneer supplies',
  vistagenomics: 'Vista genomics',
  voucherredemption: 'Redemption office',
};

const formatServiceName = (service: string) => {
  const key = normalizeServiceKey(service);
  const override = SERVICE_LABEL_OVERRIDES[key];
  if (override) {
    return override;
  }

  let name = service;

  // Strip common prefixes/suffixes if present (defensive; journals vary).
  if (name.startsWith('$') && name.endsWith(';')) {
    name = name.slice(1, -1);
  }

  name = name.replace(/_/g, ' ');
  if (!name) {
    return service;
  }
  return name.charAt(0).toUpperCase() + name.slice(1);
};

const a11yProps = (index: number) => ({
  id: `carrier-tab-${index}`,
  'aria-controls': `carrier-tabpanel-${index}`,
});

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
  // updates system data, but carriers are separate endpoints).
  useEffect(() => {
    const onBackendChanged = () => {
      void refreshCurrentCarrier();
      void loadMyCarriers();
    };
    window.addEventListener('edcaBackendChanged', onBackendChanged);
    return () => window.removeEventListener('edcaBackendChanged', onBackendChanged);
  }, [refreshCurrentCarrier, loadMyCarriers]);

  const handleCarrierViewTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    // Tab index 0 is the left-most tab.
    // We want Market on the left and Cargo on the right.
    setCarrierViewTab(newValue === 0 ? 'market' : 'cargo');
  };

  const dockedIdentity: CarrierIdentity | null =
    currentCarrierInfo && currentCarrierInfo.docked_at_carrier
      ? currentCarrierInfo.carrier
      : null;

  // Periodically refresh the current carrier snapshot while docked so that
  // market/cargo changes written to the journal are reflected without a full
  // page reload. This complements the event-driven colonisation updates.
  useEffect(() => {
    // Only poll while we are actually docked at a carrier.
    if (!dockedIdentity) {
      return;
    }

    const POLL_INTERVAL_MS = 5000;
    const id = window.setInterval(() => {
      // Use the background refresh variant so we don't toggle loading state or
      // clear the visible UI, avoiding header "jiggle".
      void refreshCurrentCarrier();
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(id);
    };
  }, [dockedIdentity, refreshCurrentCarrier]);

  const dockedServicesRaw = dockedIdentity?.services ?? [];
  const visibleDockedServices = dockedServicesRaw.filter(
    (s) => !HIDDEN_SERVICE_KEYS.has(normalizeServiceKey(s)),
  );
  const visibleDockedServicesSorted = [...visibleDockedServices].sort((a, b) =>
    formatServiceName(a).localeCompare(formatServiceName(b)),
  );

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
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            flexWrap: 'wrap',
            gap: 2,
            mb: 2,
          }}
        >
          <Box>
            <Typography variant="h6" gutterBottom>
              Current carrier
            </Typography>
            {currentCarrierLoading && (
              <Typography variant="caption" color="text.secondary">
                Loading carrier information...
              </Typography>
            )}
            {!dockedIdentity && !currentCarrierLoading && (
              <Typography variant="body2" color="text.secondary">
                You are not currently docked at a fleet carrier. Dock at your own or squadron carrier
                to see its details here.
              </Typography>
            )}
            {!currentCarrierLoading && dockedIdentity && (
              <Typography variant="body1">
                {dockedIdentity.name}{' '}
                {dockedIdentity.callsign && (
                  <Typography
                    component="span"
                    variant="body2"
                    color="text.secondary"
                    sx={{ ml: 1 }}
                  >
                    ({dockedIdentity.callsign})
                  </Typography>
                )}
              </Typography>
            )}
          </Box>

          {/* Manual refresh removed: state should update automatically via
              journal/Market.json updates + backend change-bus long-poll. */}

          {dockedIdentity && (
            <>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                {dockedIdentity.docking_access && (
                  <Chip
                    label={`Access: ${formatDockingAccess(dockedIdentity.docking_access)}`}
                    variant="outlined"
                    size="small"
                  />
                )}
                {dockedIdentity.last_seen_system && (
                  <Chip
                    label={`Last seen: ${dockedIdentity.last_seen_system}`}
                    variant="outlined"
                    size="small"
                  />
                )}
                {currentCarrierState?.total_cargo_tonnage != null && (
                  <Chip
                    label={`Cargo: ${currentCarrierState.total_cargo_tonnage.toLocaleString()} t`}
                    variant="outlined"
                    size="small"
                  />
                )}
              </Stack>

              {visibleDockedServicesSorted.length > 0 && (
                <Stack
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  flexWrap="wrap"
                  useFlexGap
                  sx={{ mt: 1 }}
                >
                  <Typography variant="caption" color="text.secondary">
                    Services:
                  </Typography>
                  {visibleDockedServicesSorted.map((service) => (
                    <Chip
                      key={service}
                      label={formatServiceName(service)}
                      size="small"
                      variant="outlined"
                    />
                  ))}
                </Stack>
              )}

            </>
          )}
        </Box>

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

        {!myCarriersLoading && (!myCarriers || (myCarriers.own_carriers.length === 0 &&
          myCarriers.squadron_carriers.length === 0)) && (
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

interface CarrierIdentityListProps {
  carriers: CarrierIdentity[];
  dockedCarrierId: number | null;
  dockedCarrierServices?: string[] | null;
}

const CarrierIdentityList = ({
  carriers,
  dockedCarrierId,
  dockedCarrierServices,
}: CarrierIdentityListProps) => {
  return (
    <Stack spacing={1}>
      {carriers.map((carrier) => {
        const isDockedHere =
          dockedCarrierId !== null && carrier.carrier_id !== null
            ? dockedCarrierId === carrier.carrier_id
            : false;

        return (
          <Paper
            key={`${carrier.carrier_id ?? carrier.market_id ?? carrier.name}`}
            variant="outlined"
            sx={{
              p: 1.5,
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', md: 'center' },
              gap: 1.5,
              bgcolor: isDockedHere ? 'action.selected' : 'background.default',
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" noWrap>
                {carrier.name}
              </Typography>
              {(() => {
                const callsign = carrier.callsign || 'No callsign';
                const baseServices = carrier.services ?? [];

                // Only force the services to match the current carrier when:
                // - This row represents the carrier we're docked at, AND
                // - That carrier is one we own.
                const services =
                  isDockedHere &&
                  carrier.role === 'own' &&
                  dockedCarrierServices != null
                    ? dockedCarrierServices
                    : baseServices;
                const visible = services.filter(
                  (s) => !HIDDEN_SERVICE_KEYS.has(normalizeServiceKey(s)),
                );
                if (visible.length === 0) {
                  return (
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {callsign}
                    </Typography>
                  );
                }
                const visibleSorted = [...visible].sort((a, b) =>
                  formatServiceName(a).localeCompare(formatServiceName(b)),
                );
                return (
                  <Typography variant="caption" color="text.secondary">
                    {callsign}: Services: {visibleSorted.map((s) => formatServiceName(s)).join(', ')}
                  </Typography>
                );
              })()}
            </Box>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ mt: { xs: 0.5, md: 0 }, alignSelf: { xs: 'flex-start', md: 'center' } }}
            >
              {carrier.last_seen_system && (
                <Chip
                  label={carrier.last_seen_system}
                  size="small"
                  variant="outlined"
                  sx={{ maxWidth: 200 }}
                />
              )}
              {isDockedHere && (
                <Chip label="Currently docked" color="primary" size="small" />
              )}
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
};

interface CarrierCargoSectionProps {
  cargo: CarrierCargoItem[];
  totalCargoTonnage: number | null;
  totalCapacityTonnage: number | null;
  freeSpaceTonnage: number | null;
  spaceUsage: {
    total_capacity?: number | null;
    crew?: number | null;
    module_packs?: number | null;
    cargo?: number | null;
    cargo_space_reserved?: number | null;
    free_space?: number | null;
  } | null;
  snapshotTime: string;
  buyOrders: CarrierOrder[];
}

const CarrierCargoSection = ({
  cargo,
  totalCargoTonnage,
  totalCapacityTonnage,
  freeSpaceTonnage,
  spaceUsage,
  snapshotTime,
  buyOrders,
}: CarrierCargoSectionProps) => {
  const buyOrderCommodities = new Set(
    (buyOrders || []).map((o) => o.commodity_name),
  );

  const outstandingBuyTonnage =
    (buyOrders || []).reduce(
      // Remaining amounts should be non-negative, but be defensive: if the
      // backend/journals ever yield a negative, treat it as 0.
      (sum, order) => sum + (order.remaining_amount < 0 ? 0 : order.remaining_amount),
      0,
    ) ?? 0;

  // Compute free space after all buy orders using the carrier's SpaceUsage breakdown
  // when available (this is the authoritative view, including module/service usage).
  //
  // TotalCapacity - (Crew + ModulePacks) - Cargo - CargoSpaceReserved
  //
  // This should not go negative in valid journal data; if it does, it indicates
  // an inconsistent snapshot.
  const freeAfterBuyOrdersTonnage = (() => {
    // If we have SpaceUsage, compute directly from its breakdown.
    // TotalCapacity - Crew - ModulePacks - Cargo - CargoSpaceReserved
    if (spaceUsage?.total_capacity != null) {
      const crew = spaceUsage.crew ?? 0;
      const modulePacks = spaceUsage.module_packs ?? 0;
      const cargoUsed = spaceUsage.cargo ?? 0;

      // IMPORTANT:
      // CarrierStats.SpaceUsage.CargoSpaceReserved does not always update
      // immediately when the commander tweaks buy orders (some sessions only
      // emit CarrierTradeOrder deltas, and CarrierStats can lag).
      //
      // For a responsive UI, treat *current* buy orders as the reservation
      // source.
      const reserved = outstandingBuyTonnage;

      return spaceUsage.total_capacity - crew - modulePacks - cargoUsed - reserved;
    }

    // Fallback when SpaceUsage breakdown is unavailable:
    // Use the backend-provided FreeSpace (already accounts for modules/services).
    // This value typically includes buy-order reservation, so it's the best we can do.
    return freeSpaceTonnage;
  })();

  if (!cargo || cargo.length === 0) {
    return (
      <Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Carrier hold summary.
        </Typography>

        {(totalCargoTonnage != null || totalCapacityTonnage != null || freeSpaceTonnage != null) && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
            {totalCargoTonnage != null && (
              <Chip
                label={`Total cargo in hold: ${totalCargoTonnage.toLocaleString()} t`}
                variant="outlined"
                size="small"
              />
            )}
            {freeAfterBuyOrdersTonnage != null && (
              <Chip
                label={`Free after all buy orders: ${freeAfterBuyOrdersTonnage.toLocaleString()} t`}
                variant="outlined"
                size="small"
              />
            )}
            {totalCapacityTonnage != null && (
              <Chip
                label={`Capacity: ${totalCapacityTonnage.toLocaleString()} t`}
                variant="outlined"
                size="small"
              />
            )}
            {outstandingBuyTonnage > 0 && (
              <Chip
                label={`Outstanding buy orders: ${outstandingBuyTonnage.toLocaleString()} t`}
                variant="outlined"
                size="small"
                color="warning"
              />
            )}
          </Stack>
        )}

        <Typography variant="body2" color="text.secondary">
          No per-commodity carrier inventory snapshot is available locally.
          The list below only shows per-commodity rows when the carrier market has active SELL stock
          (Market.json Stock &gt; 0 / journal Stock/Outstanding).
          If you have cargo in the hold but no active sell orders, this list will be empty.
        </Typography>

        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Snapshot: {new Date(snapshotTime).toLocaleString()}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Market-stock snapshot (SELL orders).
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        Snapshot: {new Date(snapshotTime).toLocaleString()}
        {totalCargoTonnage != null ? ` • Total cargo: ${totalCargoTonnage.toLocaleString()} t` : ''}
      </Typography>
      <Divider sx={{ mb: 1 }} />
      <Stack spacing={1.5}>
        {cargo.map((item) => (
          <Box
            key={item.commodity_name}
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 1,
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" noWrap>
                {item.commodity_name_localised}
                {buyOrderCommodities.has(item.commodity_name) && (
                  <Typography component="span" variant="caption" color="warning.main" sx={{ ml: 1 }}>
                    (Buy order)
                  </Typography>
                )}
              </Typography>
            </Box>
            <Box sx={{ textAlign: 'right' }}>
              <Typography variant="body2">
                {item.stock.toLocaleString()} t
                {typeof item.capacity === 'number' && (
                  <Typography
                    component="span"
                    variant="body2"
                    color="text.secondary"
                    sx={{ ml: 0.5 }}
                  >
                    / {item.capacity.toLocaleString()} t
                  </Typography>
                )}
              </Typography>
              {typeof item.reserved === 'number' && item.reserved > 0 && (
                <Typography variant="caption" color="text.secondary">
                  {item.reserved.toLocaleString()} t reserved
                </Typography>
              )}
            </Box>
          </Box>
        ))}
      </Stack>
    </Box>
  );
};

interface CarrierMarketSectionProps {
  buyOrders: CarrierOrder[];
  sellOrders: CarrierOrder[];
}

const CarrierMarketSection = ({ buyOrders, sellOrders }: CarrierMarketSectionProps) => {
  const hasAnyOrders = (buyOrders && buyOrders.length > 0) || (sellOrders && sellOrders.length > 0);

  if (!hasAnyOrders) {
    return (
      <Typography variant="body2" color="text.secondary">
        No market orders are currently available from the journals. Once carrier trade order events
        are observed, buy and sell orders will be listed here.
      </Typography>
    );
  }

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Current carrier market orders.
      </Typography>
      <Divider sx={{ mb: 2 }} />

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
          gap: 2,
        }}
      >
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Buy orders
          </Typography>
          {buyOrders.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No buy orders active.
            </Typography>
          ) : (
            <OrderList orders={buyOrders} />
          )}
        </Box>

        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Sell orders
          </Typography>
          {sellOrders.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No sell orders active.
            </Typography>
          ) : (
            <OrderList orders={sellOrders} />
          )}
        </Box>
      </Box>
    </Box>
  );
};

const OrderList = ({ orders }: { orders: CarrierOrder[] }) => {
  return (
    <Stack spacing={1.5}>
      {orders.map((order, index) => (
        <Paper
          key={`${order.commodity_name}-${order.price}-${index}`}
          variant="outlined"
          sx={{ p: 1.5, bgcolor: 'background.default' }}
        >
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 1,
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" noWrap>
                {order.commodity_name_localised}
              </Typography>
            </Box>
            <Box sx={{ textAlign: 'right' }}>
              <Typography variant="body2">
                {order.price.toLocaleString()} CR/t
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {order.remaining_amount.toLocaleString()} /{' '}
                {order.original_amount.toLocaleString()} t
              </Typography>
            </Box>
          </Box>
        </Paper>
      ))}
    </Stack>
  );
};
