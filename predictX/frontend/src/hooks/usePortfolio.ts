import { useQuery } from '@tanstack/react-query';
import { useAccount } from 'wagmi';
import { fetchUserPositions, fetchUserTransactions, fetchUserSummary } from '../lib/api';

export function useUserPositions() {
  const { address } = useAccount();
  return useQuery({
    queryKey: ['user-positions', address],
    queryFn: () => fetchUserPositions(address!),
    enabled: !!address,
    refetchInterval: 10_000,
  });
}

export function useUserTransactions() {
  const { address } = useAccount();
  return useQuery({
    queryKey: ['user-transactions', address],
    queryFn: () => fetchUserTransactions(address!),
    enabled: !!address,
    refetchInterval: 15_000,
  });
}

export function useUserSummary() {
  const { address } = useAccount();
  return useQuery({
    queryKey: ['user-summary', address],
    queryFn: () => fetchUserSummary(address!),
    enabled: !!address,
    refetchInterval: 15_000,
  });
}
