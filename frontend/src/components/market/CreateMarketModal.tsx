import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAccount } from 'wagmi';
import { useCreateMarket } from '../../hooks/useCreateMarket';

interface CreateMarketModalProps {
  onClose: () => void;
}

const STEP_LABEL: Record<string, string> = {
  idle: '',
  minting: 'Step 1 — Minting USDC...',
  approving: 'Step 2 — Approving USDC...',
  creating: 'Step 3 — Creating market...',
  success: '',
};

export default function CreateMarketModal({ onClose }: CreateMarketModalProps) {
  const [question, setQuestion] = useState('');
  const [initialLiquidity, setInitialLiquidity] = useState(10000);
  const [deadlineDays, setDeadlineDays] = useState(30);

  const { address, isConnected } = useAccount();
  const { create, reset, step, isLoading, createdMarketId, error } = useCreateMarket(address);
  const navigate = useNavigate();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    create(question.trim(), initialLiquidity, deadlineDays);
  }

  function handleGoToMarket() {
    if (createdMarketId !== null) navigate(`/market/${createdMarketId}`);
    onClose();
  }

  function handleClose() {
    reset();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-slate-800 border border-slate-700 rounded-2xl p-6 mx-4 shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-slate-100">Create Market</h2>
          <button
            onClick={handleClose}
            className="text-slate-400 hover:text-slate-200 transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>

        {step === 'success' ? (
          <div className="space-y-4">
            <div className="rounded-lg bg-emerald-900/30 border border-emerald-700/50 p-4 text-sm text-emerald-300">
              Market created successfully!
              {createdMarketId !== null && ` Market #${createdMarketId}`}
            </div>
            <div className="flex gap-2">
              {createdMarketId !== null && (
                <button
                  onClick={handleGoToMarket}
                  className="flex-1 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors"
                >
                  View Market
                </button>
              )}
              <button
                onClick={handleClose}
                className="flex-1 py-2 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {!isConnected && (
              <p className="text-xs text-amber-400 bg-amber-900/20 border border-amber-700/40 rounded-lg px-3 py-2">
                Connect your wallet to provide liquidity and create a market.
              </p>
            )}

            <div>
              <label className="block text-xs text-slate-400 mb-1">Question</label>
              <textarea
                placeholder="Will X happen by Y date?"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                rows={3}
                disabled={isLoading}
                className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-blue-500 resize-none disabled:opacity-50"
                required
              />
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Initial Liquidity (USDC) — from your wallet
              </label>
              <input
                type="number"
                min={100}
                step={100}
                value={initialLiquidity}
                onChange={e => setInitialLiquidity(Number(e.target.value))}
                disabled={isLoading}
                className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Deadline (days from now)
              </label>
              <input
                type="number"
                min={1}
                max={365}
                value={deadlineDays}
                onChange={e => setDeadlineDays(Number(e.target.value))}
                disabled={isLoading}
                className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
            </div>

            {isLoading && (
              <p className="text-xs text-blue-400">{STEP_LABEL[step]}</p>
            )}

            {error && (
              <p className="text-xs text-rose-400">{(error as Error).message.slice(0, 150)}</p>
            )}

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="flex-1 py-2 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !isConnected || !question.trim()}
                className="flex-1 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? STEP_LABEL[step] : 'Create Market'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
