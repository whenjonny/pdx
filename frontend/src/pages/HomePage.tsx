import { useState, useMemo, useCallback, useEffect } from 'react';
import { useMarkets, usePlatformStats } from '../hooks/useMarkets';
import { formatUSDC } from '../lib/format';
import MarketList from '../components/market/MarketList';
import CreateMarketModal from '../components/market/CreateMarketModal';

const CATEGORIES = ['All', 'Crypto', 'Politics', 'Sports', 'Tech', 'General'] as const;
const SORT_OPTIONS = [
  { value: 'trending', label: 'Trending' },
  { value: 'volume', label: 'Volume' },
  { value: 'newest', label: 'Newest' },
  { value: 'ending_soon', label: 'Ending Soon' },
] as const;

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export default function HomePage() {
  const [showCreate, setShowCreate] = useState(false);
  const [category, setCategory] = useState<string>('All');
  const [sort, setSort] = useState<string>('trending');
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebounce(searchInput, 300);

  const params = useMemo(() => ({
    ...(category !== 'All' && { category: category.toLowerCase() }),
    sort,
    ...(debouncedSearch && { search: debouncedSearch }),
    status: 'active' as const,
  }), [category, sort, debouncedSearch]);

  const { data: markets, isLoading, error } = useMarkets(params);
  const { data: stats } = usePlatformStats();

  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchInput(e.target.value);
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Stats Banner */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
          <StatCard label="Total Markets" value={String(stats.total_markets)} />
          <StatCard label="Active Markets" value={String(stats.active_markets)} />
          <StatCard
            label="Total Volume"
            value={`$${formatUSDC(BigInt(stats.total_volume))}`}
          />
          <StatCard label="Evidence Submitted" value={String(stats.total_evidence)} />
        </div>
      )}

      {/* Header row */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Prediction Markets</h1>
          <p className="text-sm text-slate-400 mt-1">
            Evidence-driven AI prediction markets on Base
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors shrink-0"
        >
          + Create Market
        </button>
      </div>

      {/* Filters row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        {/* Category tabs */}
        <div className="flex gap-1 overflow-x-auto pb-1">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                category === cat
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800/50 text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Search + Sort */}
        <div className="flex gap-2 shrink-0">
          <div className="relative">
            <input
              type="text"
              placeholder="Search markets..."
              value={searchInput}
              onChange={handleSearchChange}
              className="w-48 pl-8 pr-3 py-1.5 rounded-lg text-sm bg-slate-800/50 border border-slate-700/50 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors"
            />
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <select
            value={sort}
            onChange={e => setSort(e.target.value)}
            className="px-3 py-1.5 rounded-lg text-sm bg-slate-800/50 border border-slate-700/50 text-slate-200 focus:outline-none focus:border-blue-500/50 transition-colors cursor-pointer"
          >
            {SORT_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Market grid */}
      <MarketList markets={markets} isLoading={isLoading} error={error ?? null} />

      {/* Create modal */}
      {showCreate && <CreateMarketModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className="text-lg font-bold text-slate-100">{value}</div>
    </div>
  );
}
