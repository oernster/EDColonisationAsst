import { Box, Chip, Stack, Typography } from '@mui/material';

import { CarrierBalanceHistory } from '../../types/fleetCarriers';

interface CarrierBalanceHistorySectionProps {
  history?: CarrierBalanceHistory | null;
}

/** Local date and time, which is what a commander can compare against. */
const stamp = (iso: string): string => new Date(iso).toLocaleString();

/** Date alone, for the window summary where the time of day adds nothing. */
const day = (iso: string): string => new Date(iso).toLocaleDateString();

/** Signed, so a movement reads as a direction rather than a bare number. */
const signedCredits = (value: number): string =>
  `${value > 0 ? '+' : ''}${value.toLocaleString()} CR`;

/**
 * The carrier's balance over time.
 *
 * Worth being blunt about what this is not. It is not an upkeep bill, because
 * no such thing exists in the journal to read: the reserve balance never moves
 * in the readings, and the movements that do occur are trade income, tritium,
 * crew changes and upkeep mixed together with nothing to separate them. So no
 * movement here is labelled with a cause, and none should be.
 *
 * What it is good for is the shape of the money: whether the carrier is paying
 * for itself over a run, and what the largest recent movements were.
 */
export const CarrierBalanceHistorySection = ({
  history,
}: CarrierBalanceHistorySectionProps) => {
  if (!history || history.current_balance == null) {
    return null;
  }

  const { net_change: netChange, observed_from: from, observed_to: to } = history;
  const gained = (netChange ?? 0) >= 0;

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Balance over time
      </Typography>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {netChange != null && (
          <Chip
            label={`Net: ${signedCredits(netChange)}`}
            size="small"
            variant="outlined"
            color={gained ? 'success' : 'warning'}
          />
        )}
        {from && to && (
          <Chip
            label={`Observed ${day(from)} to ${day(to)}`}
            size="small"
            variant="outlined"
          />
        )}
        <Chip
          label={`${history.movements.toLocaleString()} movements`}
          size="small"
          variant="outlined"
        />
      </Stack>

      {history.entries.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          {history.entries.map((entry) => (
            <Box
              key={`${entry.recorded_at}-${entry.balance}`}
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 2,
                py: 0.5,
                borderBottom: 1,
                borderColor: 'divider',
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {stamp(entry.recorded_at)}
              </Typography>
              <Typography
                variant="caption"
                color={entry.change >= 0 ? 'success.main' : 'warning.main'}
                sx={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
              >
                {signedCredits(entry.change)}
              </Typography>
              <Typography
                variant="caption"
                sx={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
              >
                {entry.balance.toLocaleString()} CR
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      <Typography
        variant="caption"
        color="text.secondary"
        component="p"
        sx={{ mt: 1.5 }}
      >
        No cause is shown against a movement because the journal does not record
        one. Upkeep, tritium, crew changes and trade income all arrive as the
        same thing: a balance that has changed. The journal is also only written
        while you are playing, so quiet periods are gaps rather than flat lines.
      </Typography>
    </Box>
  );
};
