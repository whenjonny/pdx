import { useWriteContract, useWaitForTransactionReceipt, useReadContract } from 'wagmi';
import { parseUnits } from 'viem';
import { PDX_MARKET_ADDRESS, PDX_MARKET_ABI, MOCK_USDC_ADDRESS, MOCK_USDC_ABI, USDC_DECIMALS } from '../config/contracts';

export function useApproveUSDC() {
  const { writeContract, data: hash, isPending, error } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function approve(amount: string) {
    writeContract({
      address: MOCK_USDC_ADDRESS,
      abi: MOCK_USDC_ABI,
      functionName: 'approve',
      args: [PDX_MARKET_ADDRESS, parseUnits(amount, USDC_DECIMALS)],
    });
  }

  return { approve, isPending, isConfirming, isSuccess, error };
}

export function useAllowance(owner: `0x${string}` | undefined) {
  return useReadContract({
    address: MOCK_USDC_ADDRESS,
    abi: MOCK_USDC_ABI,
    functionName: 'allowance',
    args: owner ? [owner, PDX_MARKET_ADDRESS] : undefined,
    query: { enabled: !!owner, refetchInterval: 5_000 },
  });
}

export function useBuyYes() {
  const { writeContract, data: hash, isPending, error } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function buy(marketId: number, usdcAmount: string) {
    writeContract({
      address: PDX_MARKET_ADDRESS,
      abi: PDX_MARKET_ABI,
      functionName: 'buyYes',
      args: [BigInt(marketId), parseUnits(usdcAmount, USDC_DECIMALS)],
    });
  }

  return { buy, isPending, isConfirming, isSuccess, error };
}

export function useBuyNo() {
  const { writeContract, data: hash, isPending, error } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function buy(marketId: number, usdcAmount: string) {
    writeContract({
      address: PDX_MARKET_ADDRESS,
      abi: PDX_MARKET_ABI,
      functionName: 'buyNo',
      args: [BigInt(marketId), parseUnits(usdcAmount, USDC_DECIMALS)],
    });
  }

  return { buy, isPending, isConfirming, isSuccess, error };
}

export function useSell() {
  const { writeContract, data: hash, isPending, error } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function sell(marketId: number, isYes: boolean, tokenAmount: string) {
    writeContract({
      address: PDX_MARKET_ADDRESS,
      abi: PDX_MARKET_ABI,
      functionName: 'sell',
      args: [BigInt(marketId), isYes, parseUnits(tokenAmount, USDC_DECIMALS)],
    });
  }

  return { sell, isPending, isConfirming, isSuccess, error };
}

export function useRedeem() {
  const { writeContract, data: hash, isPending, error } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function redeem(marketId: number) {
    writeContract({
      address: PDX_MARKET_ADDRESS,
      abi: PDX_MARKET_ABI,
      functionName: 'redeem',
      args: [BigInt(marketId)],
    });
  }

  return { redeem, isPending, isConfirming, isSuccess, error };
}

export function useCreatorClaimable(marketId: number) {
  return useReadContract({
    address: PDX_MARKET_ADDRESS,
    abi: PDX_MARKET_ABI,
    functionName: 'getCreatorClaimable',
    args: [BigInt(marketId)],
    query: { refetchInterval: 5_000 },
  });
}

export function useWithdrawCreatorFunds() {
  const { writeContract, data: hash, isPending, error, reset } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function withdraw(marketId: number) {
    writeContract({
      address: PDX_MARKET_ADDRESS,
      abi: PDX_MARKET_ABI,
      functionName: 'withdrawCreatorFunds',
      args: [BigInt(marketId)],
    });
  }

  return { withdraw, isPending, isConfirming, isSuccess, error, reset };
}
