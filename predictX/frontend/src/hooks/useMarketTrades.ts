import { useQuery } from '@tanstack/react-query';
import { fetchMarketTrades } from '../lib/api';

export function useMarketTrades(marketId: number) {
  return useQuery({
    queryKey: ['market-trades', marketId],
    queryFn: () => fetchMarketTrades(marketId),
    refetchInterval: 10_000,
  });
}
