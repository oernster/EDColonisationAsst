import { Box, Chip, Divider, Stack, Typography } from '@mui/material';
import {
  CarrierCargoItem,
  CarrierOrder,
  CarrierSpaceUsage,
} from '../../types/fleetCarriers';

interface CarrierCargoSectionProps {
  cargo: CarrierCargoItem[];
  totalCargoTonnage: number | null;
  totalCapacityTonnage: number | null;
  freeSpaceTonnage: number | null;
  spaceUsage: CarrierSpaceUsage | null;
  snapshotTime: string;
  holdSnapshotTime: string | null;
  unaccountedTonnage: number | null;
  buyOrders: CarrierOrder[];
}

/**
 * How the per-commodity hold stands against the carrier's own total.
 *
 * The breakdown comes from the market export, which the game rewrites only when
 * you dock and open the carrier's commodity market. CarrierStats reports the
 * total continuously, so a difference between them is tonnage that moved by a
 * route the journal does not record. Saying so is the point: a stale breakdown
 * that looks current is worse than one that admits its age.
 */
const reconciliation = (
  unaccountedTonnage: number | null,
): { label: string; colour: 'success' | 'warning' } | null => {
  if (unaccountedTonnage == null) return null;
  if (unaccountedTonnage === 0) {
    return { label: 'Matches carrier total', colour: 'success' };
  }
  const verb = unaccountedTonnage > 0 ? 'more' : 'less';
  return {
    label: `Carrier reports ${Math.abs(unaccountedTonnage).toLocaleString()} t ${verb}`,
    colour: 'warning',
  };
};

/**
 * Tonnage still outstanding across every buy order.
 *
 * Remaining amounts should be non-negative; be defensive anyway, since if the
 * backend/journals ever yield a negative, treat it as 0.
 */
const outstandingTonnage = (buyOrders: CarrierOrder[]): number =>
  (buyOrders || []).reduce(
    (sum, order) => sum + (order.remaining_amount < 0 ? 0 : order.remaining_amount),
    0,
  );

/**
 * Free space once every buy order has been filled.
 *
 * Computed from the carrier's SpaceUsage breakdown when there is one, since
 * that is the authoritative view and includes module and service usage:
 *
 *   TotalCapacity - (Crew + ModulePacks) - Cargo - CargoSpaceReserved
 *
 * It should not go negative on valid journal data; if it does, the snapshot
 * is inconsistent.
 *
 * IMPORTANT: CargoSpaceReserved is NOT used as the reservation. It does not
 * always update when the commander tweaks buy orders, because some sessions
 * emit only CarrierTradeOrder deltas and CarrierStats lags behind. Current
 * buy orders are the responsive source and are what this uses.
 */
const freeAfterBuyOrders = (
  spaceUsage: CarrierSpaceUsage | null,
  freeSpaceTonnage: number | null,
  reserved: number,
): number | null => {
  if (spaceUsage?.total_capacity == null) {
    // Without the breakdown, fall back to the backend's FreeSpace, which
    // already accounts for modules and services. It typically includes
    // buy-order reservation, so it is the best available answer.
    return freeSpaceTonnage;
  }

  const crew = spaceUsage.crew ?? 0;
  const modulePacks = spaceUsage.module_packs ?? 0;
  const cargoUsed = spaceUsage.cargo ?? 0;

  return spaceUsage.total_capacity - crew - modulePacks - cargoUsed - reserved;
};

/**
 * What is in the hold, plus how much room is left.
 *
 * Two shapes, because the per-commodity breakdown needs a market export the
 * commander may never have produced: with none there are still tonnage totals
 * worth showing; the empty case says exactly what to do about it.
 */
export const CarrierCargoSection = ({
  cargo,
  totalCargoTonnage,
  totalCapacityTonnage,
  freeSpaceTonnage,
  spaceUsage,
  snapshotTime,
  holdSnapshotTime,
  unaccountedTonnage,
  buyOrders,
}: CarrierCargoSectionProps) => {
  const buyOrderCommodities = new Set((buyOrders || []).map((o) => o.commodity_name));
  const outstandingBuyTonnage = outstandingTonnage(buyOrders);
  const freeAfterBuyOrdersTonnage = freeAfterBuyOrders(
    spaceUsage,
    freeSpaceTonnage,
    outstandingBuyTonnage,
  );
  const reconciled = reconciliation(unaccountedTonnage);

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
          No per-commodity breakdown is available yet. Elite Dangerous writes no carrier
          inventory event, so the breakdown comes from the carrier&apos;s own market export.
          Dock at the carrier and open its commodity market once; the hold below then
          lists every commodity aboard, whether or not it carries a sell order.
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
        Carrier hold, heaviest first.
      </Typography>
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
        {reconciled != null && (
          <Chip
            label={reconciled.label}
            variant="outlined"
            size="small"
            color={reconciled.colour}
          />
        )}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        {holdSnapshotTime != null
          ? `Hold read from the carrier market at ${new Date(holdSnapshotTime).toLocaleString()}, plus your trades since`
          : `Snapshot: ${new Date(snapshotTime).toLocaleString()}`}
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
