import { useState, useEffect } from 'react';
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { parseUnits } from 'viem';
import { useTokenBalance } from '../../hooks/useUserPositions';
import { useSell } from '../../hooks/useTrading';
import { formatTokens } from '../../lib/format';
import { PDX_MARKET_ADDRESS, OUTCOME_TOKEN_ABI, USDC_DECIMALS } from '../../config/contracts';
import type { MarketFromAPI } from '../../types/market';

interface SellPanelProps {
  market: MarketFromAPI;
}

export default function SellPanel({ market }: SellPanelProps) {
  const [side, setSide] = useState<'YES' | 'NO'>('YES');
  const [amount, setAmount] = useState('');
  const { address } = useAccount();
  const { data: yesBalance } = useTokenBalance(market.yesToken as `0x${string}`, address);
  const { data: noBalance } = useTokenBalance(market.noToken as `0x${string}`, address);
  const { sell, isPending: isSelling, isConfirming: isSellConfirming, isSuccess: sellSuccess, error: sellError } = useSell();

  // Token approval for the outcome token
  const { writeContract: approveToken, data: approveHash, isPending: isApprovePending } = useWriteContract();
  const { isLoading: isApproveConfirming, isSuccess: approveSuccess } = useWaitForTransactionReceipt({ hash: approveHash });

  const yesAmt = (yesBalance as bigint) ?? 0n;
  const noAmt = (noBalance as bigint) ?? 0n;
  const activeBalance = side === 'YES' ? yesAmt : noAmt;
  const hasTokens = yesAmt > 0n || noAmt > 0n;

  const isLocked = Date.now() / 1000 >= market.lockTime;
  const isExpired = Date.now() / 1000 >= market.deadline;
  const disabled = isLocked || isExpired || market.resolved;

  const parsedAmount = (() => {
    const num = parseFloat(amount);
    if (isNaN(num) || num <= 0) return 0n;
    return BigInt(Math.floor(num * 10 ** USDC_DECIMALS));
  })();

  const canSell = !disabled && parsedAmount > 0n && parsedAmount <= activeBalance && !!address;

  // Estimate USDC return from selling tokens (CPMM)
  const reserveYes = Number(market.reserveYes);
  const reserveNo = Number(market.reserveNo);
  const k = reserveYes * reserveNo;
  const sellAmt = Number(parsedAmount);
  let estimatedUSDC = 0;
  if (sellAmt > 0) {
    if (side === 'YES') {
      // Selling YES tokens: add to YES reserve, remove from NO reserve
      const newReserveYes = reserveYes + sellAmt;
      const newReserveNo = k / newReserveYes;
      const usdcOut = reserveNo - newReserveNo;
      estimatedUSDC = usdcOut * 0.997; // 0.3% fee
    } else {
      const newReserveNo = reserveNo + sellAmt;
      const newReserveYes = k / newReserveNo;
      const usdcOut = reserveYes - newReserveYes;
      estimatedUSDC = usdcOut * 0.997;
    }
  }

  // After approval succeeds, execute the sell
  useEffect(() => {
    if (approveSuccess && amount && parsedAmount > 0n) {
      sell(market.id, side === 'YES', amount);
    }
  }, [approveSuccess]);

  // Reset form on successful sell
  useEffect(() => {
    if (sellSuccess) {
      setAmount('');
    }
  }, [sellSuccess]);

  function handleSell() {
    if (!canSell) return;
    const tokenAddress = side === 'YES' ? market.yesToken : market.noToken;
    // Approve the market contract to spend outcome tokens, then sell
    approveToken({
      address: tokenAddress as `0x${string}`,
      abi: OUTCOME_TOKEN_ABI,
      functionName: 'approve',
      args: [PDX_MARKET_ADDRESS, parseUnits(amount, USDC_DECIMALS)],
    });
  }

  const isPending = isApprovePending || isApproveConfirming || isSelling || isSellConfirming;

  if (!address) {
    return (
      <div className="py-8 text-center text-sm text-slate-500">
        Connect wallet to sell tokens
      </div>
    );
  }

  if (!hasTokens) {
    return (
      <div className="py-8 text-center text-sm text-slate-500">
        You have no tokens to sell in this market
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {disabled && (
        <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-800/30 text-amber-400 text-sm">
          {market.resolved ? 'Market settled -- selling is closed.' : isExpired ? 'Market expired' : 'Trading locked (30min before deadline)'}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => { setSide('YES'); setAmount(''); }}
          disabled={yesAmt === 0n}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
            side === 'YES'
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          Sell YES
        </button>
        <button
          onClick={() => { setSide('NO'); setAmount(''); }}
          disabled={noAmt === 0n}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
            side === 'NO'
              ? 'bg-rose-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          Sell NO
        </button>
      </div>

      <div className="p-3 rounded-lg bg-slate-900/50 text-sm">
        <div className="flex justify-between text-slate-400">
          <span>Your {side} tokens</span>
          <span className="text-slate-200">{formatTokens(activeBalance)}</span>
        </div>
      </div>

      <div>
        <label className="text-xs text-slate-500 mb-1 block">Token amount to sell</label>
        <input
          type="number"
          min="0"
          step="0.01"
          placeholder="0.00"
          value={amount}
          onChange={e => setAmount(e.target.value)}
          disabled={disabled}
          className="w-full px-3 py-2.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50"
        />
        <div className="flex justify-end mt-1">
          <button
            onClick={() => setAmount((Number(activeBalance) / 1e6).toString())}
            disabled={disabled || activeBalance === 0n}
            className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
          >
            Max
          </button>
        </div>
      </div>

      {estimatedUSDC > 0 && (
        <div className="p-3 rounded-lg bg-slate-900/50 text-xs text-slate-400 space-y-1">
          <div className="flex justify-between">
            <span>Est. USDC return</span>
            <span className="text-slate-200">${(estimatedUSDC / 1e6).toFixed(4)}</span>
          </div>
          <div className="flex justify-between">
            <span>Fee rate</span>
            <span className="text-slate-200">0.3%</span>
          </div>
        </div>
      )}

      <button
        onClick={handleSell}
        disabled={!canSell || isPending}
        className="w-full py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-amber-600 text-white hover:bg-amber-500"
      >
        {isPending ? 'Confirming...' : `Sell ${side}`}
      </button>

      {sellSuccess && (
        <p className="text-xs text-emerald-400">Sold successfully!</p>
      )}
      {sellError && (
        <p className="text-xs text-rose-400">{sellError.message?.slice(0, 100)}</p>
      )}
    </div>
  );
}
