import { Box, Chip, Stack, Typography } from '@mui/material';
import { CarrierIdentity, CarrierState } from '../../types/fleetCarriers';
import { CarrierTransitChip } from './CarrierTransitChip';
import {
  formatDockingAccess,
  formatServiceName,
  visibleServicesSorted,
} from './carrierServices';

interface CurrentCarrierHeaderProps {
  /** The carrier the commander is standing on, or null when they are not. */
  dockedIdentity: CarrierIdentity | null;
  carrierState: CarrierState | null;
  loading: boolean;
}

/**
 * The top of the "Current carrier" card: which carrier, where it is, and the
 * few facts worth reading at a glance.
 *
 * It describes the CARRIER, which is never docked anywhere: it holds station
 * in a star system, or it has a jump booked. Whether the commander happens to
 * be aboard is a separate fact, said once in a caption, and it does not decide
 * whether the carrier is shown. Being docked at a station on the other side of
 * the bubble does not stop your carrier holding six thousand tonnes.
 */
export const CurrentCarrierHeader = ({
  dockedIdentity,
  carrierState,
  loading,
}: CurrentCarrierHeaderProps) => {
  // The carrier to describe. Falling back to the state's own identity is what
  // lets the panel keep showing your carrier while you are docked somewhere
  // else entirely, which is most of the time.
  const identity = dockedIdentity ?? carrierState?.identity ?? null;
  const aboard = carrierState?.commander_aboard ?? false;
  const services = visibleServicesSorted(identity?.services ?? []);

  return (
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
        {loading && (
          <Typography variant="caption" color="text.secondary">
            Loading carrier information...
          </Typography>
        )}
        {!identity && !loading && (
          <Typography variant="body2" color="text.secondary">
            No fleet carrier has been seen in your journals yet. Once your carrier
            reports in, its state appears here whether or not you are aboard.
          </Typography>
        )}
        {!loading && identity && (
          <Typography variant="body1">
            {identity.name}{' '}
            {identity.callsign && (
              <Typography
                component="span"
                variant="body2"
                color="text.secondary"
                sx={{ ml: 1 }}
              >
                ({identity.callsign})
              </Typography>
            )}
          </Typography>
        )}
        {!loading && identity && !aboard && (
          /* About the COMMANDER, not the carrier. The carrier is wherever it
             is; this only says the reading was taken when you were last on
             board, so nothing here claims to be live. */
          <Typography variant="caption" color="text.secondary">
            You are not aboard. Showing this carrier as of the last time you were.
          </Typography>
        )}
      </Box>

      {/* Manual refresh removed: state should update automatically via
          journal/Market.json updates + backend change-bus long-poll. */}

      {identity && (
        <>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            {identity.docking_access && (
              <Chip
                label={`Access: ${formatDockingAccess(identity.docking_access)}`}
                variant="outlined"
                size="small"
              />
            )}
            {identity.last_seen_system && (
              /* A carrier is never "docked" and is never merely "last seen":
                 it is parked in a star system or in transit between two. The
                 system named here is where it is. */
              <Chip
                label={`Current star system: ${identity.last_seen_system}`}
                variant="outlined"
                size="small"
              />
            )}
            {/* Sits beside the system rather than replacing it: a booked jump
                does not move the carrier, it leaves at its departure time. */}
            <CarrierTransitChip transit={identity.transit} />
            {carrierState?.total_cargo_tonnage != null && (
              <Chip
                label={`Cargo: ${carrierState.total_cargo_tonnage.toLocaleString()} t`}
                variant="outlined"
                size="small"
              />
            )}
          </Stack>

          {services.length > 0 && (
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
              {services.map((service) => (
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
  );
};
