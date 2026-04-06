import { useState, useEffect } from 'react';
import { useWriteContract, useWaitForTransactionReceipt, useReadContract } from 'wagmi';
import { parseUnits, parseEventLogs } from 'viem';
import { useQueryClient } from '@tanstack/react-query';
import {
  PDX_MARKET_ADDRESS,
  PDX_MARKET_ABI,
  MOCK_USDC_ADDRESS,
  MOCK_USDC_ABI,
  USDC_DECIMALS,
} from '../config/contracts';

/**
 * Create Market — on-chain flow
 *
 * All transactions are signed by the connected wallet (the user pays the liquidity).
 *
 * Step 1 — Mint (skipped if balance is sufficient)
 *   MockUSDC.mint(owner, shortfall + 100 USDC buffer)
 *   Only needed in dev/testnet where MockUSDC is freely mintable.
 *
 * Step 2 — Approve (skipped if allowance is already sufficient)
 *   MockUSDC.approve(PDXMarket, uint256.max)
 *   Grants the market contract permission to pull USDC from the user's wallet.
 *
 * Step 3 — Create market
 *   PDXMarket.createMarket(question, conditionId, deadline, initialLiquidity)
 *   The contract pulls `initialLiquidity` USDC from msg.sender and seeds the AMM pool.
 *   The caller becomes the market's `creator`.
 *
 * After confirmation, the MarketCreated event is parsed from the receipt to
 * retrieve the new market ID without an extra RPC call.
 */
const ZERO_BYTES32 = `0x${'00'.repeat(32)}` as `0x${string}`;

interface PendingParams {
  question: string;
  liquidityRaw: bigint;
  deadline: bigint;
}

export type CreateMarketStep = 'idle' | 'minting' | 'approving' | 'creating' | 'success';

export function useCreateMarket(owner: `0x${string}` | undefined) {
  const queryClient = useQueryClient();
  const [pendingParams, setPendingParams] = useState<PendingParams | null>(null);
  const [createdMarketId, setCreatedMarketId] = useState<number | null>(null);

  // Read USDC balance
  const { data: balance, refetch: refetchBalance } = useReadContract({
    address: MOCK_USDC_ADDRESS,
    abi: MOCK_USDC_ABI,
    functionName: 'balanceOf',
    args: owner ? [owner] : undefined,
    query: { enabled: !!owner },
  });

  // Read allowance
  const { data: allowance, refetch: refetchAllowance } = useReadContract({
    address: MOCK_USDC_ADDRESS,
    abi: MOCK_USDC_ABI,
    functionName: 'allowance',
    args: owner ? [owner, PDX_MARKET_ADDRESS] : undefined,
    query: { enabled: !!owner },
  });

  // Step 1: Mint
  const { writeContract: writeMint, data: mintHash, isPending: isMintPending, error: mintError, reset: resetMint } = useWriteContract();
  const { isLoading: isMintConfirming, isSuccess: isMintSuccess } = useWaitForTransactionReceipt({ hash: mintHash });

  // Step 2: Approve
  const { writeContract: writeApprove, data: approveHash, isPending: isApprovePending, error: approveError, reset: resetApprove } = useWriteContract();
  const { isLoading: isApproveConfirming, isSuccess: isApproveSuccess } = useWaitForTransactionReceipt({ hash: approveHash });

  // Step 3: Create market
  const { writeContract: writeCreate, data: createHash, isPending: isCreatePending, error: createError, reset: resetCreate } = useWriteContract();
  const { isLoading: isCreateConfirming, isSuccess: isCreateSuccess, data: createReceipt } = useWaitForTransactionReceipt({ hash: createHash });

  function doApprove(params: PendingParams) {
    const sufficient = allowance !== undefined && (allowance as bigint) >= params.liquidityRaw;
    if (sufficient) {
      doCreate(params);
    } else {
      writeApprove({
        address: MOCK_USDC_ADDRESS,
        abi: MOCK_USDC_ABI,
        functionName: 'approve',
        args: [PDX_MARKET_ADDRESS, 2n ** 256n - 1n],
      });
    }
  }

  function doCreate(params: PendingParams) {
    writeCreate({
      address: PDX_MARKET_ADDRESS,
      abi: PDX_MARKET_ABI,
      functionName: 'createMarket',
      args: [params.question, ZERO_BYTES32, params.deadline, params.liquidityRaw],
    });
  }

  // After mint confirmed → proceed to approve
  useEffect(() => {
    if (!isMintSuccess || !pendingParams) return;
    refetchBalance();
    doApprove(pendingParams);
  }, [isMintSuccess]);

  // After approve confirmed → proceed to create
  useEffect(() => {
    if (!isApproveSuccess || !pendingParams) return;
    refetchAllowance();
    doCreate(pendingParams);
  }, [isApproveSuccess]);

  // After create confirmed → parse market ID
  useEffect(() => {
    if (!isCreateSuccess || !createReceipt) return;
    try {
      const logs = parseEventLogs({
        abi: PDX_MARKET_ABI as Parameters<typeof parseEventLogs>[0]['abi'],
        eventName: 'MarketCreated',
        logs: createReceipt.logs,
      });
      if (logs.length > 0) {
        setCreatedMarketId(Number((logs[0] as { args: { marketId: bigint } }).args.marketId));
      }
    } catch { /* market ID unknown */ }
    queryClient.invalidateQueries({ queryKey: ['markets'] });
  }, [isCreateSuccess, createReceipt]);

  function create(question: string, initialLiquidity: number, deadlineDays: number, _category?: string, _resolutionSource?: string) {
    if (!owner) return;
    const raw = parseUnits(String(initialLiquidity), USDC_DECIMALS);
    const deadline = BigInt(Math.floor(Date.now() / 1000) + deadlineDays * 86400);
    const params: PendingParams = { question, liquidityRaw: raw, deadline };

    setPendingParams(params);
    setCreatedMarketId(null);
    resetMint();
    resetApprove();
    resetCreate();

    const currentBalance = (balance as bigint | undefined) ?? 0n;
    if (currentBalance < raw) {
      // Mint the shortfall (+ small buffer)
      const mintAmount = raw - currentBalance + parseUnits('100', USDC_DECIMALS);
      writeMint({
        address: MOCK_USDC_ADDRESS,
        abi: MOCK_USDC_ABI,
        functionName: 'mint',
        args: [owner, mintAmount],
      });
    } else {
      doApprove(params);
    }
  }

  function reset() {
    setPendingParams(null);
    setCreatedMarketId(null);
    resetMint();
    resetApprove();
    resetCreate();
  }

  const isMinting = isMintPending || isMintConfirming;
  const isApproving = isApprovePending || isApproveConfirming;
  const isCreating = isCreatePending || isCreateConfirming;

  let step: CreateMarketStep = 'idle';
  if (isCreateSuccess) step = 'success';
  else if (isCreating) step = 'creating';
  else if (isApproving) step = 'approving';
  else if (isMinting) step = 'minting';

  return {
    create,
    reset,
    step,
    isLoading: isMinting || isApproving || isCreating,
    createdMarketId,
    error: mintError || approveError || createError,
    balance: balance as bigint | undefined,
  };
}
