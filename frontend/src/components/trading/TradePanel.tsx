import { useState, useEffect } from 'react';
import { useAccount } from 'wagmi';
import { useBuyYes, useBuyNo, useApproveUSDC, useAllowance } from '../../hooks/useTrading';
import { useUSDCBalance } from '../../hooks/useMockUSDC';
import { useHasEvidence } from '../../hooks/useEvidence';
import { formatUSDC, parseUSDC } from '../../lib/format';
import type { MarketFromAPI } from '../../types/market';

interface TradePanelProps {
  market: MarketFromAPI;
}

export default function TradePanel({ market }: TradePanelProps) {
  const [side, setSide] = useState<'YES' | 'NO'>('YES');
  const [amount, setAmount] = useState('');
  const { address } = useAccount();
  const { data: balance } = useUSDCBalance(address);
  const { data: allowance } = useAllowance(address);
  const { data: hasEvidence } = useHasEvidence(market.id, address);
  const feeRate = hasEvidence ? 0.001 : 0.003;
  const feeLabel = hasEvidence ? '0.1%' : '0.3%';
  const { approve, isPending: isApproving, isConfirming: isApproveConfirming, isSuccess: approveSuccess } = useApproveUSDC();
  const buyYes = useBuyYes();
  const buyNo = useBuyNo();
  const activeBuy = side === 'YES' ? buyYes : buyNo;

  const parsedAmount = parseUSDC(amount);
  const needsApproval = allowance !== undefined && parsedAmount > (allowance as bigint);
  const isLocked = Date.now() / 1000 >= market.lockTime;
  const isExpired = Date.now() / 1000 >= market.deadline;
  const canTrade = !isLocked && !isExpired && !market.resolved && parsedAmount > 0n;

  useEffect(() => {
    if (approveSuccess) {
      activeBuy.buy(market.id, amount);
    }
  }, [approveSuccess]);

  // Reset form on successful buy
  useEffect(() => {
    if (activeBuy.isSuccess) {
      setAmount('');
    }
  }, [activeBuy.isSuccess]);

  function handleTrade() {
    if (!amount || parsedAmount === 0n) return;
    if (needsApproval) {
      approve(amount);
    } else {
      activeBuy.buy(market.id, amount);
    }
  }

  const isPending = isApproving || isApproveConfirming || activeBuy.isPending || activeBuy.isConfirming;

  // Estimate tokens out (CPMM calc)
  const reserveYes = Number(market.reserveYes);
  const reserveNo = Number(market.reserveNo);
  const k = reserveYes * reserveNo;
  const netInput = Number(parsedAmount) * (1 - feeRate);
  let estimatedTokens = 0;
  let priceImpact = 0;
  if (side === 'YES' && netInput > 0) {
    const newReserveYes = k / (reserveNo + netInput);
    estimatedTokens = reserveYes - newReserveYes;
    // Price impact: difference between spot price and effective price
    const spotPrice = reserveNo / (reserveYes + reserveNo);
    const effectivePrice = Number(parsedAmount) / estimatedTokens;
    priceImpact = estimatedTokens > 0 ? Math.abs(effectivePrice - spotPrice) / spotPrice * 100 : 0;
  } else if (side === 'NO' && netInput > 0) {
    const newReserveNo = k / (reserveYes + netInput);
    estimatedTokens = reserveNo - newReserveNo;
    priceImpact = estimatedTokens > 0 ? Math.abs((Number(parsedAmount) / estimatedTokens) - (reserveYes / (reserveYes + reserveNo))) / (reserveYes / (reserveYes + reserveNo)) * 100 : 0;
  }

  const priceImpactColor = priceImpact > 5 ? 'text-rose-400' : priceImpact > 2 ? 'text-amber-400' : 'text-slate-200';

  return (
    <div className="space-y-4">
      {(isLocked || isExpired || market.resolved) && (
        <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-800/30 text-amber-400 text-sm">
          {market.resolved ? 'Market settled -- trading is closed.' : isExpired ? 'Market expired' : 'Trading locked (30min before deadline)'}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => setSide('YES')}
          className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
            side === 'YES'
              ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/30'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
          }`}
        >
          YES {Math.round(market.priceYes * 100)}%
        </button>
        <button
          onClick={() => setSide('NO')}
          className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
            side === 'NO'
              ? 'bg-rose-600 text-white shadow-lg shadow-rose-900/30'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
          }`}
        >
          NO {Math.round(market.priceNo * 100)}%
        </button>
      </div>

      <div>
        <label className="text-xs text-slate-500 mb-1.5 block">Amount (USDC)</label>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm">$</span>
          <input
            type="number"
            min="0"
            step="0.01"
            placeholder="0.00"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            className="w-full pl-7 pr-3 py-2.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-colors"
          />
        </div>
        {balance !== undefined && (
          <div className="flex justify-between mt-1.5 text-xs text-slate-500">
            <span>Balance: {formatUSDC(balance as bigint)} USDC</span>
            <button
              onClick={() => setAmount((Number(balance) / 1e6).toString())}
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              Max
            </button>
          </div>
        )}
      </div>

      {estimatedTokens > 0 && (
        <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/30 text-xs space-y-2">
          <div className="flex justify-between text-slate-400">
            <span>Est. tokens received</span>
            <span className="text-slate-200 font-medium">{(estimatedTokens / 1e6).toFixed(4)} {side}</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>Price impact</span>
            <span className={`font-medium ${priceImpactColor}`}>
              {priceImpact < 0.01 ? '<0.01' : priceImpact.toFixed(2)}%
            </span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>Fee</span>
            <span className={hasEvidence ? 'text-emerald-400' : 'text-slate-200'}>{feeLabel}</span>
          </div>
        </div>
      )}

      <button
        onClick={handleTrade}
        disabled={!canTrade || isPending || !address}
        className={`w-full py-2.5 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
          side === 'YES'
            ? 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-900/20'
            : 'bg-rose-600 text-white hover:bg-rose-500 shadow-lg shadow-rose-900/20'
        }`}
      >
        {!address
          ? 'Connect Wallet'
          : isPending
            ? 'Confirming...'
            : needsApproval
              ? `Approve & Buy ${side}`
              : `Buy ${side}`}
      </button>

      {activeBuy.isSuccess && (
        <p className="text-xs text-emerald-400">Purchase successful!</p>
      )}
      {(activeBuy.error || buyYes.error || buyNo.error) && (
        <p className="text-xs text-rose-400">
          {(activeBuy.error || buyYes.error || buyNo.error)?.message?.slice(0, 100)}
        </p>
      )}
    </div>
  );
}
