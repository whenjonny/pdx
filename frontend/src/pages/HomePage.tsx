import { useState } from 'react';
import MarketList from '../components/market/MarketList';
import CreateMarketModal from '../components/market/CreateMarketModal';

export default function HomePage() {
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Prediction Markets</h1>
          <p className="text-sm text-slate-400 mt-1">
            Evidence-driven AI prediction markets on Base
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors"
        >
          + Create Market
        </button>
      </div>
      <MarketList />
      {showCreate && <CreateMarketModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}
