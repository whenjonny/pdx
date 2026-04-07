import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useMarket } from '../hooks/useMarkets';
import { formatUSDC } from '../lib/format';
import CountdownTimer from '../components/market/CountdownTimer';
import TradePanel from '../components/trading/TradePanel';
import SellPanel from '../components/trading/SellPanel';
import PositionDisplay from '../components/trading/PositionDisplay';
import ActivityFeed from '../components/market/ActivityFeed';
import EvidenceList from '../components/evidence/EvidenceList';
import EvidenceSubmitForm from '../components/evidence/EvidenceSubmitForm';
import MiroFishProbability from '../components/prediction/MiroFishProbability';

type Tab = 'trade' | 'sell' | 'activity';

export default function MarketPage() {
  const { id } = useParams<{ id: string }>();
  const marketId = parseInt(id || '0');
  const { data: market, isLoading, error } = useMarket(marketId);
  const [activeTab, setActiveTab] = useState<Tab>('trade');

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

  const yesPercent = Math.round(market.priceYes * 100);
  const noPercent = Math.round(market.priceNo * 100);

  const tabs: { key: Tab; label: string }[] = [
    { key: 'trade', label: 'Trade' },
    { key: 'sell', label: 'Sell' },
    { key: 'activity', label: 'Activity' },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Back link */}
      <Link to="/" className="text-sm text-blue-400 hover:text-blue-300">&larr; Back to markets</Link>

      {/* Header */}
      <div className="mt-6 mb-6">
        <h1 className="text-2xl font-bold text-slate-100 mb-3">{market.question}</h1>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-400">
          <CountdownTimer deadline={market.deadline} lockTime={market.lockTime} />
          <span className="flex items-center gap-1">
            <span className="text-slate-500">Vol</span>
            <span className="text-slate-300">${formatUSDC(BigInt(market.totalDeposited))}</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="text-slate-500">Fees</span>
            <span className="text-slate-300">${formatUSDC(BigInt(market.feesAccrued))}</span>
          </span>
          {market.resolved && (
            <span className={`font-medium ${market.outcome ? 'text-emerald-400' : 'text-rose-400'}`}>
              Settled: {market.outcome ? 'YES' : 'NO'}
            </span>
          )}
        </div>
      </div>

      {/* Large probability display — AMM real transaction price */}
      <div className="mb-8">
        <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Market Price</h3>
        <div className="flex gap-4">
          <div className="flex-1 rounded-xl bg-emerald-900/20 border border-emerald-800/30 p-5 text-center">
            <div className="text-4xl font-bold text-emerald-400">{yesPercent}%</div>
            <div className="text-sm text-emerald-400/70 mt-1 font-medium">YES</div>
          </div>
          <div className="flex-1 rounded-xl bg-rose-900/20 border border-rose-800/30 p-5 text-center">
            <div className="text-4xl font-bold text-rose-400">{noPercent}%</div>
            <div className="text-sm text-rose-400/70 mt-1 font-medium">NO</div>
          </div>
        </div>
      </div>

      {/* Two column layout */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left column (2/3) */}
        <div className="lg:col-span-2 space-y-4">
          {/* Tabs */}
          <div className="rounded-xl bg-slate-800/50 border border-slate-700/50">
            <div className="flex border-b border-slate-700/50">
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-5 py-3 text-sm font-medium transition-colors ${
                    activeTab === tab.key
                      ? 'text-blue-400 border-b-2 border-blue-400'
                      : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="p-5">
              {activeTab === 'trade' && <TradePanel market={market} />}
              {activeTab === 'sell' && <SellPanel market={market} />}
              {activeTab === 'activity' && <ActivityFeed marketId={marketId} />}
            </div>
          </div>
        </div>

        {/* Right column (1/3) */}
        <div className="space-y-4">
          <PositionDisplay market={market} />
          <MiroFishProbability marketId={marketId} ammPriceYes={market.priceYes} />
          <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
            <h3 className="text-sm font-medium text-slate-300 mb-4">
              Evidence{market.evidenceCount > 0 ? ` \u00B7 ${market.evidenceCount} submitted` : ''}
            </h3>
            {!market.resolved && (
              <div className="mb-4">
                <EvidenceSubmitForm marketId={marketId} />
              </div>
            )}
            <EvidenceList marketId={marketId} />
          </div>
        </div>
      </div>
    </div>
  );
}
