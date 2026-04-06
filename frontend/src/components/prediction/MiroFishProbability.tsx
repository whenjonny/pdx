import { usePrediction } from '../../hooks/usePrediction';

interface MiroFishProbabilityProps {
  marketId: number;
}

export default function MiroFishProbability({ marketId }: MiroFishProbabilityProps) {
  const { data: prediction, isLoading, error } = usePrediction(marketId);

  if (isLoading) {
    return (
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
        <h3 className="text-sm font-medium text-slate-300 mb-3">AI Prediction</h3>
        <div className="animate-pulse h-16 bg-slate-700 rounded-lg" />
      </div>
    );
  }

  if (error || !prediction) {
    return (
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
        <h3 className="text-sm font-medium text-slate-300 mb-3">AI Prediction</h3>
        <p className="text-sm text-slate-500">Unavailable</p>
      </div>
    );
  }

  const yesPercent = Math.round(prediction.probability_yes * 100);

  return (
    <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-slate-300">AI Prediction</h3>
        <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/50 text-indigo-400">
          {prediction.source}
        </span>
      </div>

      <div className="text-center mb-3">
        <div className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
          {yesPercent}%
        </div>
        <div className="text-xs text-slate-500 mt-1">
          Probability YES | Confidence: {Math.round(prediction.confidence * 100)}%
        </div>
      </div>

      {prediction.reasoning && (
        <p className="text-xs text-slate-400 border-t border-slate-700/50 pt-3 leading-relaxed">
          {prediction.reasoning}
        </p>
      )}
    </div>
  );
}
