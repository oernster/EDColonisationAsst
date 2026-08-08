import { Box, Chip, Stack, Typography } from '@mui/material';
import { CarrierIdentity, CarrierState } from '../../types/fleetCarriers';
import {
  formatDockingAccess,
  formatServiceName,
  visibleServicesSorted,
} from './carrierServices';

interface CurrentCarrierHeaderProps {
  /** The carrier the commander is docked at, or null when docked elsewhere. */
  dockedIdentity: CarrierIdentity | null;
  carrierState: CarrierState | null;
  loading: boolean;
}

/**
 * The top of the "Current carrier" card: who you are docked at and the few
 * facts worth reading at a glance.
 *
 * Three states, in the order they occur: loading, not docked, docked. Only
 * the last shows chips, because the others have nothing to put in them.
 */
export const CurrentCarrierHeader = ({
  dockedIdentity,
  carrierState,
  loading,
}: CurrentCarrierHeaderProps) => {
  const services = visibleServicesSorted(dockedIdentity?.services ?? []);

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
        {!dockedIdentity && !loading && (
          <Typography variant="body2" color="text.secondary">
            You are not currently docked at a fleet carrier. Dock at your own or squadron carrier
            to see its details here.
          </Typography>
        )}
        {!loading && dockedIdentity && (
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
