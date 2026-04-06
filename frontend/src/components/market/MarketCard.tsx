import { Link } from 'react-router-dom';
import type { MarketFromAPI } from '../../types/market';
import { formatUSDC, formatCountdown } from '../../lib/format';
import PriceBar from './PriceBar';

interface MarketCardProps {
  market: MarketFromAPI;
}

export default function MarketCard({ market }: MarketCardProps) {
  const expired = Date.now() / 1000 >= market.deadline;

  return (
    <Link
      to={`/market/${market.id}`}
      className="block p-5 rounded-xl bg-slate-800/50 border border-slate-700/50 hover:border-slate-600 transition-all hover:bg-slate-800/80"
    >
      <div className="flex justify-between items-start mb-3">
        <h3 className="text-base font-medium text-slate-100 leading-snug flex-1 mr-3">
          {market.question}
        </h3>
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

      <PriceBar priceYes={market.price_yes} className="mb-3" />

      <div className="flex gap-4 text-xs text-slate-500">
        <span>Volume: ${formatUSDC(BigInt(market.total_deposited))}</span>
        <span>Evidence: {market.evidence_count}</span>
      </div>
    </Link>
  );
}
