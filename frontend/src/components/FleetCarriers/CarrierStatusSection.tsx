import { Alert, Box, Chip, Divider, Stack, Typography } from '@mui/material';

import {
  CarrierBalanceHistory,
  CarrierCrewMember,
  CarrierStatus,
} from '../../types/fleetCarriers';
import { CarrierBalanceHistorySection } from './CarrierBalanceHistorySection';
import { formatServiceName } from './carrierServices';

interface CarrierStatusSectionProps {
  status: CarrierStatus | null;
  balanceHistory?: CarrierBalanceHistory | null;
}

/** Jump range is reported to one decimal, which is the precision the game shows. */
const JUMP_RANGE_DECIMALS = 1;

/** The captain is not a service the commander can use, so it reads separately. */
const CAPTAIN_ROLE = 'captain';

const tonnes = (value: number): string => `${value.toLocaleString()} t`;

const credits = (value: number): string => `${value.toLocaleString()} CR`;

const lightYears = (value: number): string =>
  `${value.toFixed(JUMP_RANGE_DECIMALS)} ly`;

/**
 * One labelled reading.
 *
 * Rendered as a chip so a row of them wraps sensibly on a cockpit tablet,
 * where this view is as likely to be read as on a monitor.
 */
const reading = (label: string, value: string) => (
  <Chip key={label} label={`${label}: ${value}`} size="small" variant="outlined" />
);

/**
 * The crew member holding a role, when one has been hired.
 *
 * Activated says the position has been paid for; enabled says the service is
 * currently switched on. A hired service that has been switched off is worth
 * distinguishing, because from the outside it looks the same as one that was
 * never bought.
 */
const crewLabel = (member: CarrierCrewMember): string => {
  const role = formatServiceName(member.role);
  const name = member.name ? ` (${member.name})` : '';
  const suspended = member.enabled === false ? ', switched off' : '';
  return `${role}${name}${suspended}`;
};

/**
 * The carrier's own systems: what it runs on, what it is worth and who crews it.
 *
 * Deliberately separate from the cargo view. The hold answers what the carrier
 * is carrying for you; this answers whether the carrier can go anywhere, pay
 * for itself and offer the services you are relying on.
 *
 * Nothing here is invented. Every reading is drawn from the newest CarrierStats
 * event, and anything that event did not carry is simply left out rather than
 * shown as zero: a fuel gauge reading empty because the journal was quiet is
 * worse than no gauge at all.
 */
export const CarrierStatusSection = ({
  status,
  balanceHistory,
}: CarrierStatusSectionProps) => {
  if (!status) {
    return (
      <Typography variant="body2" color="text.secondary">
        No CarrierStats event has been seen for this carrier yet, so its fuel,
        finances and crew are not known. Docking at the carrier or opening its
        management panel makes the game write one.
      </Typography>
    );
  }

  const { finance } = status;

  const flight = [
    status.fuel_level != null ? reading('Fuel', tonnes(status.fuel_level)) : null,
    status.jump_range_current != null
      ? reading('Jump range', lightYears(status.jump_range_current))
      : null,
    status.jump_range_max != null
      ? reading('Maximum range', lightYears(status.jump_range_max))
      : null,
  ].filter(Boolean);

  const money = finance
    ? [
        finance.carrier_balance != null
          ? reading('Balance', credits(finance.carrier_balance))
          : null,
        finance.available_balance != null
          ? reading('Available', credits(finance.available_balance))
          : null,
        finance.reserve_balance != null
          ? reading('Reserve', credits(finance.reserve_balance))
          : null,
        finance.reserve_percent != null
          ? reading('Reserve rate', `${finance.reserve_percent}%`)
          : null,
      ].filter(Boolean)
    : [];

  const tax = finance
    ? [
        finance.tax_rate_refuel != null
          ? reading('Refuel tax', `${finance.tax_rate_refuel}%`)
          : null,
        finance.tax_rate_repair != null
          ? reading('Repair tax', `${finance.tax_rate_repair}%`)
          : null,
        finance.tax_rate_rearm != null
          ? reading('Restock tax', `${finance.tax_rate_rearm}%`)
          : null,
      ].filter(Boolean)
    : [];

  const captain = status.crew.find(
    (member) => member.role.toLowerCase() === CAPTAIN_ROLE && member.activated,
  );
  const services = status.crew.filter(
    (member) => member.role.toLowerCase() !== CAPTAIN_ROLE,
  );
  const hired = services.filter((member) => member.activated);
  const available = services.filter((member) => !member.activated);

  return (
    <Box>
      {status.pending_decommission && (
        <Alert severity="error" sx={{ mb: 2 }}>
          This carrier is scheduled for decommissioning. When the countdown ends
          the carrier is destroyed along with anything still aboard, so move your
          cargo off it and cancel the decommission if this was not deliberate.
        </Alert>
      )}

      {flight.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Fuel and range
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {flight}
          </Stack>
        </Box>
      )}

      {(money.length > 0 || tax.length > 0) && (
        <>
          <Divider sx={{ my: 2 }} />
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Finance
            </Typography>
            {money.length > 0 && (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {money}
              </Stack>
            )}
            {tax.length > 0 && (
              <Stack
                direction="row"
                spacing={1}
                flexWrap="wrap"
                useFlexGap
                sx={{ mt: 1 }}
              >
                <Typography variant="caption" color="text.secondary">
                  Charged to visitors:
                </Typography>
                {tax}
              </Stack>
            )}
          </Box>
        </>
      )}

      {balanceHistory && (
        <>
          <Divider sx={{ my: 2 }} />
          <CarrierBalanceHistorySection history={balanceHistory} />
        </>
      )}

      {status.crew.length > 0 && (
        <>
          <Divider sx={{ my: 2 }} />
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Crew and services
            </Typography>

            {captain && (
              <Typography variant="body2" sx={{ mb: 1 }}>
                Captain: {captain.name ?? 'hired'}
              </Typography>
            )}

            {hired.length > 0 && (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {hired.map((member) => (
                  <Chip
                    key={member.role}
                    label={crewLabel(member)}
                    size="small"
                    color={member.enabled === false ? 'default' : 'success'}
                    variant="outlined"
                  />
                ))}
              </Stack>
            )}

            {available.length > 0 && (
              <Typography
                variant="caption"
                color="text.secondary"
                component="p"
                sx={{ mt: 1.5 }}
              >
                Not hired:{' '}
                {available
                  .map((member) => formatServiceName(member.role))
                  .join(', ')}
              </Typography>
            )}
          </Box>
        </>
      )}
    </Box>
  );
};
