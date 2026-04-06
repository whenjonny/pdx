import { Link } from 'react-router-dom';
import type { MarketFromAPI } from '../../types/market';
import { formatUSDC, formatCountdown } from '../../lib/format';
import PriceBar from './PriceBar';

interface MarketCardProps {
  market: MarketFromAPI;
  isOwner?: boolean;
}

export default function MarketCard({ market, isOwner }: MarketCardProps) {
  const expired = Date.now() / 1000 >= market.deadline;

  return (
    <Link
      to={`/market/${market.id}`}
      className={`block p-5 rounded-xl border transition-all hover:bg-slate-800/80 ${
        isOwner
          ? 'bg-blue-950/30 border-blue-700/50 hover:border-blue-600'
          : 'bg-slate-800/50 border-slate-700/50 hover:border-slate-600'
      }`}
    >
      <div className="flex justify-between items-start mb-3">
        <h3 className="text-base font-medium text-slate-100 leading-snug flex-1 mr-3">
          {market.question}
        </h3>
        <div className="flex items-center gap-1.5 shrink-0">
          {isOwner && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300 font-medium">
              My Market
            </span>
          )}
        {market.resolved ? (
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            market.outcome ? 'bg-emerald-900/50 text-emerald-400' : 'bg-rose-900/50 text-rose-400'
          }`}>
            {market.outcome ? 'YES' : 'NO'}
          </span>
        ) : expired ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/50 text-amber-400 font-medium">
            Pending
          </span>
        ) : (
          <span className="text-xs text-slate-500">{formatCountdown(market.deadline)}</span>
        )}
        </div>
      </div>

      <PriceBar priceYes={market.priceYes} className="mb-3" />

      <div className="flex gap-4 text-xs text-slate-500">
        <span>Volume: ${formatUSDC(BigInt(market.totalDeposited))}</span>
        <span>{market.evidenceCount === 0 ? 'No Evidence' : market.evidenceCount === 1 ? '1 Evidence' : `${market.evidenceCount} Evidences`}</span>
      </div>
    </Link>
  );
}
