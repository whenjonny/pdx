import { useState } from 'react';
import { usePrediction } from '../../hooks/usePrediction';
import MiroFishModal from './MiroFishModal';

interface MiroFishProbabilityProps {
  marketId: number;
  ammPriceYes: number;
}

export default function MiroFishProbability({ marketId, ammPriceYes }: MiroFishProbabilityProps) {
  const { data: prediction, isLoading, error } = usePrediction(marketId);
  const [showModal, setShowModal] = useState(false);

  if (isLoading) {
    return (
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
        <h3 className="text-sm font-medium text-slate-300 mb-3">AI Reference</h3>
        <div className="animate-pulse h-16 bg-slate-700 rounded-lg" />
      </div>
    );
  }

  if (error || !prediction) {
    return (
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
        <h3 className="text-sm font-medium text-slate-300 mb-3">AI Reference</h3>
        <p className="text-sm text-slate-500">Unavailable</p>
      </div>
    );
  }

  const yesPercent = Math.round(prediction.probability_yes * 100);
  const marketPercent = Math.round(ammPriceYes * 100);
  const delta = yesPercent - marketPercent;
  const deltaStr = delta > 0 ? `+${delta}%` : `${delta}%`;
  const deltaColor = delta > 0 ? 'text-emerald-400' : delta < 0 ? 'text-rose-400' : 'text-slate-400';

  return (
    <>
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5 group">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-slate-300">AI Reference</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/50 text-indigo-400">
            {prediction.source}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Probability display */}
          <div className="flex-1 text-center">
            <div className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              {yesPercent}%
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Confidence: {Math.round(prediction.confidence * 100)}%
            </div>
            {delta !== 0 && (
              <div className={`text-xs mt-1 font-medium ${deltaColor}`}>
                {deltaStr} vs market
              </div>
            )}
          </div>

          {/* Detail button */}
          <button
            onClick={() => setShowModal(true)}
            className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600/80 to-purple-600/80 hover:from-indigo-500 hover:to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 hover:shadow-indigo-500/40 transition-all hover:scale-105 active:scale-95"
            title="View AI Analysis"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
              <path d="M11 8v6M8 11h6" />
            </svg>
          </button>
        </div>

        <div className="mt-3 pt-2 border-t border-slate-700/50 flex items-center justify-between">
          <span className="text-[10px] text-slate-600">For reference only</span>
          <button
            onClick={() => setShowModal(true)}
            className="text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            View details &rarr;
          </button>
        </div>
      </div>

      {showModal && (
        <MiroFishModal
          marketId={marketId}
          ammPriceYes={ammPriceYes}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  );
}
