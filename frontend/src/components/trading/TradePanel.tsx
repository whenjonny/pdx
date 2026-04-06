import { useState, useEffect } from 'react';
import { useAccount } from 'wagmi';
import { useBuyYes, useBuyNo, useApproveUSDC, useAllowance } from '../../hooks/useTrading';
import { useUSDCBalance } from '../../hooks/useMockUSDC';
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
  const { approve, isPending: isApproving, isConfirming: isApproveConfirming, isSuccess: approveSuccess } = useApproveUSDC();
  const buyYes = useBuyYes();
  const buyNo = useBuyNo();
  const activeBuy = side === 'YES' ? buyYes : buyNo;

  const parsedAmount = parseUSDC(amount);
  const needsApproval = allowance !== undefined && parsedAmount > (allowance as bigint);
  const isLocked = Date.now() / 1000 >= market.lock_time;
  const isExpired = Date.now() / 1000 >= market.deadline;
  const canTrade = !isLocked && !isExpired && !market.resolved && parsedAmount > 0n;

  useEffect(() => {
    if (approveSuccess) {
      activeBuy.buy(market.id, amount);
    }
  }, [approveSuccess]);

  function handleTrade() {
    if (!amount || parsedAmount === 0n) return;
    if (needsApproval) {
      approve(amount);
    } else {
      activeBuy.buy(market.id, amount);
    }
  }

  const isPending = isApproving || isApproveConfirming || activeBuy.isPending || activeBuy.isConfirming;

  // Estimate tokens out (simplified CPMM calc)
  const reserveYes = Number(market.reserve_yes);
  const reserveNo = Number(market.reserve_no);
  const k = reserveYes * reserveNo;
  const netInput = Number(parsedAmount) * 0.997; // 0.3% fee
  let estimatedTokens = 0;
  if (side === 'YES' && netInput > 0) {
    const newReserveYes = k / (reserveNo + netInput);
    estimatedTokens = reserveYes - newReserveYes;
  } else if (side === 'NO' && netInput > 0) {
    const newReserveNo = k / (reserveYes + netInput);
    estimatedTokens = reserveNo - newReserveNo;
  }

  return (
    <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
      <h3 className="text-sm font-medium text-slate-300 mb-4">Trade</h3>

      {(isLocked || isExpired || market.resolved) && (
        <div className="mb-4 p-3 rounded-lg bg-amber-900/20 border border-amber-800/30 text-amber-400 text-sm">
          {market.resolved ? 'Market settled' : isExpired ? 'Market expired' : 'Trading locked (30min before deadline)'}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setSide('YES')}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
            side === 'YES'
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          YES {Math.round(market.price_yes * 100)}c
        </button>
        <button
          onClick={() => setSide('NO')}
          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
            side === 'NO'
              ? 'bg-rose-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          NO {Math.round(market.price_no * 100)}c
        </button>
      </div>

      <div className="mb-4">
        <label className="text-xs text-slate-500 mb-1 block">Amount (USDC)</label>
        <input
          type="number"
          min="0"
          step="0.01"
          placeholder="0.00"
          value={amount}
          onChange={e => setAmount(e.target.value)}
          className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-sm focus:outline-none focus:border-blue-500"
        />
        {balance !== undefined && (
          <div className="flex justify-between mt-1 text-xs text-slate-500">
            <span>Balance: {formatUSDC(balance as bigint)} USDC</span>
            <button
              onClick={() => setAmount((Number(balance) / 1e6).toString())}
              className="text-blue-400 hover:text-blue-300"
            >
              Max
            </button>
          </div>
        )}
      </div>

      {estimatedTokens > 0 && (
        <div className="mb-4 p-3 rounded-lg bg-slate-900/50 text-xs text-slate-400 space-y-1">
          <div className="flex justify-between">
            <span>Est. tokens</span>
            <span className="text-slate-200">{(estimatedTokens / 1e6).toFixed(4)} {side}</span>
          </div>
          <div className="flex justify-between">
            <span>Fee rate</span>
            <span className="text-slate-200">0.3%</span>
          </div>
        </div>
      )}

      <button
        onClick={handleTrade}
        disabled={!canTrade || isPending || !address}
        className="w-full py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 text-white hover:bg-blue-500"
      >
        {!address
          ? 'Connect Wallet'
          : isPending
            ? 'Confirming...'
            : needsApproval
              ? `Approve & Buy ${side}`
              : `Buy ${side}`}
      </button>

      {(activeBuy.error || buyYes.error || buyNo.error) && (
        <p className="mt-2 text-xs text-rose-400">
          {(activeBuy.error || buyYes.error || buyNo.error)?.message?.slice(0, 100)}
        </p>
      )}
    </div>
  );
}
