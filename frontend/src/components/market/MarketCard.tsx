import { Link } from 'react-router-dom';
import type { MarketFromAPI } from '../../types/market';
import { formatUSDC, formatCountdown, formatAddress, isLocked } from '../../lib/format';
import { useChainTime } from '../../hooks/useChainTime';
import PriceBar from './PriceBar';

interface MarketCardProps {
  market: MarketFromAPI;
  isOwner?: boolean;
}

export default function MarketCard({ market, isOwner }: MarketCardProps) {
  const now = useChainTime();
  const expired = now >= market.deadline;
  const locked = isLocked(market.lockTime, now);
  const yesPercent = Math.round(market.priceYes * 100);

  return (
    <Link
      to={`/market/${market.id}`}
      className={`block p-5 rounded-xl border transition-all hover:scale-[1.01] hover:shadow-lg hover:shadow-slate-900/50 ${
        isOwner
          ? 'bg-blue-950/30 border-blue-700/50 hover:border-blue-600'
          : 'bg-slate-800/50 border-slate-700/50 hover:border-slate-600'
      }`}
    >
      {/* Status + Owner badges */}
      <div className="flex items-center gap-2 mb-3">
        {market.resolved ? (
          <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${
            market.outcome ? 'bg-emerald-900/50 text-emerald-400' : 'bg-rose-900/50 text-rose-400'
          }`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            Settled {market.outcome ? 'YES' : 'NO'}
          </span>
        ) : locked || expired ? (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-900/50 text-amber-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            Locked
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-900/50 text-emerald-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Live
          </span>
        )}
        {isOwner && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300 font-medium">
            My Market
          </span>
        )}
        {!market.resolved && !expired && (
          <span className="text-xs text-slate-500 ml-auto">{formatCountdown(market.deadline, now)}</span>
        )}
      </div>

      {/* Question */}
      <h3 className="text-base font-semibold text-slate-100 leading-snug mb-4 line-clamp-2">
        {market.question}
      </h3>

      {/* Probability highlight */}
      <div className="flex items-end justify-between mb-3">
        <div>
          <span className="text-3xl font-bold text-emerald-400">{yesPercent}%</span>
          <span className="text-sm text-slate-500 ml-1.5">chance</span>
          <div className="text-[10px] text-slate-600 mt-0.5">Market Price</div>
        </div>
        <div className="text-right">
          <div className="text-sm font-medium text-slate-300">
            ${formatUSDC(BigInt(market.totalDeposited))}
          </div>
          <div className="text-xs text-slate-500">volume</div>
        </div>
      </div>

      <PriceBar priceYes={market.priceYes} className="mb-4" />

      {/* Footer: creator + evidence */}
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{formatAddress(market.creator)}</span>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${
          market.evidenceCount > 0
            ? 'bg-blue-900/40 text-blue-300'
            : 'bg-slate-700/50 text-slate-500'
        }`}>
          {market.evidenceCount} {market.evidenceCount === 1 ? 'evidence' : 'evidences'}
        </span>
      </div>
    </Link>
  );
}
