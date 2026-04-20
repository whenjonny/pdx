import { useAccount } from 'wagmi';
import type { MarketFromAPI } from '../../types/market';
import MarketCard from './MarketCard';

interface MarketListProps {
  markets?: MarketFromAPI[];
  isLoading?: boolean;
  error?: Error | null;
}

export default function MarketList({ markets, isLoading, error }: MarketListProps) {
  const { address } = useAccount();

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
        <p className="text-lg">No markets found</p>
        <p className="text-sm mt-1">Try adjusting your filters or create a new market</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {markets.map(m => (
        <MarketCard
          key={m.id}
          market={m}
          isOwner={!!address && m.creator.toLowerCase() === address.toLowerCase()}
        />
      ))}
    </div>
  );
}
