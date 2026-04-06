import { useMarketTrades } from '../../hooks/useMarketTrades';
import { formatAddress, formatUSDC } from '../../lib/format';
import type { MarketTrade } from '../../types/market';

interface ActivityFeedProps {
  marketId: number;
}

function timeAgo(timestamp: number): string {
  const seconds = Math.floor(Date.now() / 1000) - timestamp;
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function tradeBadge(type: MarketTrade['type']) {
  switch (type) {
    case 'buy_yes':
      return <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-900/50 text-emerald-400">Buy YES</span>;
    case 'buy_no':
      return <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-rose-900/50 text-rose-400">Buy NO</span>;
    case 'sell_yes':
      return <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-900/50 text-amber-400">Sell YES</span>;
    case 'sell_no':
      return <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-900/50 text-amber-400">Sell NO</span>;
  }
}

export default function ActivityFeed({ marketId }: ActivityFeedProps) {
  const { data: trades, isLoading } = useMarketTrades(marketId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-400" />
      </div>
    );
  }

  const recentTrades = (trades ?? []).slice(0, 20);

  if (recentTrades.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-slate-500">
        No trades yet
      </div>
    );
  }

  return (
    <div className="max-h-96 overflow-y-auto">
      {recentTrades.map((trade, i) => (
        <div
          key={`${trade.tx_hash}-${i}`}
          className={`flex items-center justify-between px-3 py-2.5 text-sm ${
            i % 2 === 0 ? 'bg-slate-800/30' : ''
          }`}
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-slate-400 font-mono text-xs shrink-0">
              {formatAddress(trade.trader)}
            </span>
            {tradeBadge(trade.type)}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-slate-200 text-xs font-medium">
              ${formatUSDC(BigInt(trade.usdc_amount))}
            </span>
            <span className="text-slate-500 text-xs w-14 text-right">
              {timeAgo(trade.timestamp)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
