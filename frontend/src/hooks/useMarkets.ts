import { useQuery } from '@tanstack/react-query';
import { fetchMarkets, fetchMarket } from '../lib/api';

export function useMarkets() {
  return useQuery({
    queryKey: ['markets'],
    queryFn: fetchMarkets,
    refetchInterval: 10_000,
  });
}

export function useMarket(id: number) {
  return useQuery({
    queryKey: ['market', id],
    queryFn: () => fetchMarket(id),
    refetchInterval: 5_000,
    enabled: id >= 0,
  });
}
