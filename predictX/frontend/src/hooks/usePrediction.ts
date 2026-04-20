import { useQuery } from '@tanstack/react-query';
import { fetchPrediction } from '../lib/api';

export function usePrediction(marketId: number) {
  return useQuery({
    queryKey: ['prediction', marketId],
    queryFn: () => fetchPrediction(marketId),
    refetchInterval: 30_000,
    enabled: marketId >= 0,
  });
}
