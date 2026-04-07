import { useEffect, useRef, useState } from 'react';
import { usePrediction } from '../../hooks/usePrediction';
import { useEvidenceList } from '../../hooks/useEvidence';
import EvidenceNetworkGraph from './EvidenceNetworkGraph';

interface MiroFishModalProps {
  marketId: number;
  ammPriceYes: number;
  onClose: () => void;
}

function CircularGauge({ value, size = 160 }: { value: number; size?: number }) {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - value / 100);

  return (
    <svg width={size} height={size} className="drop-shadow-lg">
      <defs>
        <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#818cf8" />
          <stop offset="50%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#a78bfa" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Background track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#1e293b"
        strokeWidth="10"
      />
      {/* Animated arc */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="url(#gaugeGrad)"
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        filter="url(#glow)"
        className="transition-all duration-1000 ease-out"
      />
      {/* Center text */}
      <text
        x={size / 2}
        y={size / 2 - 8}
        textAnchor="middle"
        className="fill-white text-3xl font-bold"
        style={{ fontSize: '2rem', fontWeight: 700 }}
      >
        {value}%
      </text>
      <text
        x={size / 2}
        y={size / 2 + 16}
        textAnchor="middle"
        className="fill-slate-400 text-xs"
        style={{ fontSize: '0.7rem' }}
      >
        YES Probability
      </text>
    </svg>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-400 mb-1">
        <span>Confidence</span>
        <span className="text-indigo-300 font-medium">{pct}%</span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-purple-500 transition-all duration-1000 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

type ModalTab = 'analysis' | 'network';

export default function MiroFishModal({ marketId, ammPriceYes, onClose }: MiroFishModalProps) {
  const { data: prediction, isLoading } = usePrediction(marketId);
  const { data: evidence } = useEvidenceList(marketId);
  const backdropRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<ModalTab>('analysis');

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const yesPercent = prediction ? Math.round(prediction.probability_yes * 100) : 0;
  const marketPercent = Math.round(ammPriceYes * 100);
  const delta = yesPercent - marketPercent;
  const deltaStr = delta > 0 ? `+${delta}%` : `${delta}%`;
  const deltaColor = delta > 0 ? 'text-emerald-400' : delta < 0 ? 'text-rose-400' : 'text-slate-400';

  const updatedAt = prediction?.updated_at
    ? new Date(prediction.updated_at * 1000).toLocaleString()
    : null;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md animate-fadeIn"
      onClick={e => { if (e.target === backdropRef.current) onClose(); }}
    >
      <div className="relative w-full max-w-md mx-4 animate-slideUp">
        {/* Glow background effect */}
        <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500/20 via-purple-500/20 to-pink-500/20 rounded-2xl blur-xl" />

        <div className="relative rounded-2xl bg-slate-900/95 border border-slate-700/60 shadow-2xl overflow-hidden">
          {/* Animated header gradient bar */}
          <div className="h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 animate-gradientSlide" />

          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-5 pb-3">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93" />
                    <path d="M8.56 13.44A4.98 4.98 0 0 0 7 17c0 2.76 2.24 5 5 5s5-2.24 5-5-2.24-5-5-5" />
                    <circle cx="12" cy="17" r="1" fill="white" />
                    <path d="M17 2.3A9.96 9.96 0 0 1 22 11" />
                    <path d="M7 2.3A9.96 9.96 0 0 0 2 11" />
                  </svg>
                </div>
                <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-slate-900 animate-pulse" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-100">MiroFish AI</h2>
                <p className="text-[11px] text-slate-500">Prediction Engine</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-400 hover:text-slate-200 transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Tab bar */}
          <div className="flex border-b border-slate-800 mx-6">
            {([
              { key: 'analysis' as ModalTab, label: 'Analysis', icon: 'M9 19v-6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2zm0 0V9a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v10m-6 0a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2m0 0V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2z' },
              { key: 'network' as ModalTab, label: 'Network', icon: 'M12 5 L5 19 M12 5 L19 19 M5 19 L19 19' },
            ]).map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px ${
                  activeTab === tab.key
                    ? 'text-indigo-400 border-indigo-400'
                    : 'text-slate-500 border-transparent hover:text-slate-300'
                }`}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d={tab.icon} />
                </svg>
                {tab.label}
              </button>
            ))}
          </div>

          {/* Body */}
          <div className="px-6 pb-6 pt-4">
            {isLoading ? (
              <div className="flex flex-col items-center py-10">
                <div className="w-12 h-12 rounded-full border-2 border-indigo-500/30 border-t-indigo-500 animate-spin" />
                <p className="text-sm text-slate-400 mt-4">Analyzing market data...</p>
              </div>
            ) : !prediction ? (
              <div className="text-center py-10">
                <p className="text-slate-400">Prediction unavailable</p>
              </div>
            ) : activeTab === 'analysis' ? (
              <div className="space-y-5">
                {/* Gauge + Source badge */}
                <div className="flex flex-col items-center pt-2">
                  <CircularGauge value={yesPercent} />
                  <span className="mt-3 text-xs px-3 py-1 rounded-full bg-indigo-900/50 text-indigo-300 border border-indigo-700/40">
                    {prediction.source}
                  </span>
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-xl bg-slate-800/60 border border-slate-700/40 p-3 text-center">
                    <div className="text-lg font-bold text-indigo-300">{yesPercent}%</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">AI Estimate</div>
                  </div>
                  <div className="rounded-xl bg-slate-800/60 border border-slate-700/40 p-3 text-center">
                    <div className="text-lg font-bold text-slate-300">{marketPercent}%</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">Market Price</div>
                  </div>
                  <div className="rounded-xl bg-slate-800/60 border border-slate-700/40 p-3 text-center">
                    <div className={`text-lg font-bold ${deltaColor}`}>{delta === 0 ? '0%' : deltaStr}</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">Delta</div>
                  </div>
                </div>

                {/* Confidence bar */}
                <ConfidenceBar value={prediction.confidence} />

                {/* Reasoning */}
                {prediction.reasoning && (
                  <div className="rounded-xl bg-slate-800/40 border border-slate-700/30 p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2" strokeLinecap="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                      <span className="text-xs font-medium text-indigo-300">Analysis</span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">{prediction.reasoning}</p>
                  </div>
                )}

                {/* Footer */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                  <span className="text-[10px] text-slate-600 italic">For reference only</span>
                  {updatedAt && (
                    <span className="text-[10px] text-slate-600">Updated {updatedAt}</span>
                  )}
                </div>
              </div>
            ) : (
              /* Network tab */
              <div className="space-y-4">
                <EvidenceNetworkGraph
                  evidence={evidence ?? []}
                  prediction={prediction}
                  ammPriceYes={ammPriceYes}
                />
                <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                  <span className="text-[10px] text-slate-600 italic">
                    {evidence?.length ?? 0} evidence node{(evidence?.length ?? 0) !== 1 ? 's' : ''}
                  </span>
                  <span className="text-[10px] text-slate-600">Hover nodes for details</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
