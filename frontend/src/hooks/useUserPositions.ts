import { useReadContract } from 'wagmi';
import { OUTCOME_TOKEN_ABI } from '../config/contracts';

export function useTokenBalance(tokenAddress: `0x${string}` | undefined, userAddress: `0x${string}` | undefined) {
  return useReadContract({
    address: tokenAddress,
    abi: OUTCOME_TOKEN_ABI,
    functionName: 'balanceOf',
    args: userAddress ? [userAddress] : undefined,
    query: { enabled: !!tokenAddress && !!userAddress, refetchInterval: 5_000 },
  });
}
