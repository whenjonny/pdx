import { useAccount } from 'wagmi';
import { useMarkets } from '../../hooks/useMarkets';
import MarketCard from './MarketCard';

export default function MarketList() {
  const { address } = useAccount();
  const { data: markets, isLoading, error } = useMarkets();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-20 text-slate-500">
        <p>Failed to load markets</p>
        <p className="text-sm mt-1">{error.message}</p>
      </div>
    );
  }

  if (!markets?.length) {
    return (
      <div className="text-center py-20 text-slate-500">
        <p className="text-lg">No markets yet</p>
        <p className="text-sm mt-1">Deploy contracts and create a market to get started</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {markets.map(m => (
        <MarketCard key={m.id} market={m} isOwner={!!address && m.creator.toLowerCase() === address.toLowerCase()} />
      ))}
    </div>
  );
}
