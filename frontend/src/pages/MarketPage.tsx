import { useParams, Link } from 'react-router-dom';
import { useMarket } from '../hooks/useMarkets';
import { formatUSDC } from '../lib/format';
import PriceBar from '../components/market/PriceBar';
import CountdownTimer from '../components/market/CountdownTimer';
import TradePanel from '../components/trading/TradePanel';
import PositionDisplay from '../components/trading/PositionDisplay';
import EvidenceList from '../components/evidence/EvidenceList';
import EvidenceSubmitForm from '../components/evidence/EvidenceSubmitForm';
import MiroFishProbability from '../components/prediction/MiroFishProbability';

export default function MarketPage() {
  const { id } = useParams<{ id: string }>();
  const marketId = parseInt(id || '0');
  const { data: market, isLoading, error } = useMarket(marketId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (error || !market) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8">
        <Link to="/" className="text-sm text-blue-400 hover:text-blue-300">&larr; Back to markets</Link>
        <p className="text-slate-400 mt-8 text-center">Market not found</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <Link to="/" className="text-sm text-blue-400 hover:text-blue-300">&larr; Back to markets</Link>

      <div className="mt-6 mb-8">
        <h1 className="text-xl font-bold text-slate-100 mb-2">{market.question}</h1>
        <div className="flex flex-wrap gap-4 text-sm text-slate-400">
          <CountdownTimer deadline={market.deadline} lockTime={market.lockTime} />
          <span>Volume: ${formatUSDC(BigInt(market.totalDeposited))}</span>
          <span>Fees: ${formatUSDC(BigInt(market.feesAccrued))}</span>
          {market.resolved && (
            <span className={market.outcome ? 'text-emerald-400 font-medium' : 'text-rose-400 font-medium'}>
              Settled: {market.outcome ? 'YES' : 'NO'}
            </span>
          )}
        </div>
        <PriceBar priceYes={market.priceYes} className="mt-4 max-w-md" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left column: Trade + Position */}
        <div className="space-y-4">
          <TradePanel market={market} />
          <PositionDisplay market={market} />
        </div>

        {/* Middle column: AI Prediction */}
        <div className="space-y-4">
          <MiroFishProbability marketId={marketId} />
        </div>

        {/* Right column: Evidence */}
        <div className="space-y-4">
          <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
            <h3 className="text-sm font-medium text-slate-300 mb-4">
              Evidence ({market.evidenceCount})
            </h3>
            <div className="mb-4">
              <EvidenceSubmitForm marketId={marketId} />
            </div>
            <EvidenceList marketId={marketId} />
          </div>
        </div>
      </div>
    </div>
  );
}
