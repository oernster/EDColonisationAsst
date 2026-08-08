import { Box, Chip, Paper, Stack, Typography } from '@mui/material';
import { CarrierIdentity } from '../../types/fleetCarriers';
import { formatServiceName, visibleServicesSorted } from './carrierServices';

interface CarrierIdentityListProps {
  carriers: CarrierIdentity[];
  dockedCarrierId: number | null;
  dockedCarrierServices?: string[] | null;
}

const LAST_SEEN_CHIP_MAX_WIDTH = 200;

/**
 * The service line under a carrier's name: its callsign, then whatever
 * services are worth listing.
 *
 * A plain function rather than a component because it was an inline IIFE and
 * uses no hooks; calling it keeps the reconciliation identical to before.
 */
const carrierSubtitle = (
  carrier: CarrierIdentity,
  isDockedHere: boolean,
  dockedCarrierServices?: string[] | null,
) => {
  const callsign = carrier.callsign || 'No callsign';

  // Only force the services to match the current carrier when:
  // - This row represents the carrier we're docked at, AND
  // - That carrier is one we own.
  const services =
    isDockedHere && carrier.role === 'own' && dockedCarrierServices != null
      ? dockedCarrierServices
      : carrier.services ?? [];

  const visible = visibleServicesSorted(services);
  if (visible.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" noWrap>
        {callsign}
      </Typography>
    );
  }

  return (
    <Typography variant="caption" color="text.secondary">
      {callsign}: Services: {visible.map((service) => formatServiceName(service)).join(', ')}
    </Typography>
  );
};

/**
 * A carrier per row, with the one you are standing on picked out.
 *
 * Used for both the owned and the squadron lists, which differ only in what
 * is passed in.
 */
export const CarrierIdentityList = ({
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
              {carrierSubtitle(carrier, isDockedHere, dockedCarrierServices)}
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
                  sx={{ maxWidth: LAST_SEEN_CHIP_MAX_WIDTH }}
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
