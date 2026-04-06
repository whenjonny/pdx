import MarketList from '../components/market/MarketList';

export default function HomePage() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-100">Prediction Markets</h1>
        <p className="text-sm text-slate-400 mt-1">
          Evidence-driven AI prediction markets on Base
        </p>
      </div>
      <MarketList />
    </div>
  );
}
