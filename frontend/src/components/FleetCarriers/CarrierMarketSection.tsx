import { Box, Divider, Paper, Stack, Typography } from '@mui/material';
import { CarrierOrder } from '../../types/fleetCarriers';

interface CarrierMarketSectionProps {
  buyOrders: CarrierOrder[];
  sellOrders: CarrierOrder[];
}

const OrderList = ({ orders }: { orders: CarrierOrder[] }) => {
  return (
    <Stack spacing={1.5}>
      {orders.map((order, index) => (
        <Paper
          // Commodity and price do not uniquely identify an order, so the
          // index is part of the key. Orders are only ever replaced wholesale
          // by a fresh snapshot, never reordered in place.
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

/**
 * The carrier's own market: what it is buying on the left, selling on the right.
 *
 * Both columns are always drawn once there is anything at all to show, so an
 * empty side reads as "no buy orders" rather than as a missing column.
 */
export const CarrierMarketSection = ({
  buyOrders,
  sellOrders,
}: CarrierMarketSectionProps) => {
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
