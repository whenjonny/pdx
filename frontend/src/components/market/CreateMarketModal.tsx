import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAccount } from 'wagmi';
import { useCreateMarket } from '../../hooks/useCreateMarket';
import { formatUSDC } from '../../lib/format';

interface CreateMarketModalProps {
  onClose: () => void;
}

const CATEGORIES = ['General', 'Crypto', 'Politics', 'Sports', 'Tech'] as const;

const STEP_LABEL: Record<string, string> = {
  idle: '',
  minting: 'Step 1/3 — Minting USDC...',
  approving: 'Step 2/3 — Approving USDC...',
  creating: 'Step 3/3 — Creating market...',
  success: '',
};

const STEP_NUMBER: Record<string, number> = {
  minting: 1,
  approving: 2,
  creating: 3,
};

export default function CreateMarketModal({ onClose }: CreateMarketModalProps) {
  const [question, setQuestion] = useState('');
  const [category, setCategory] = useState('general');
  const [resolutionSource, setResolutionSource] = useState('');
  const [initialLiquidity, setInitialLiquidity] = useState(1000);
  const [deadlineDays, setDeadlineDays] = useState(30);

  const { address, isConnected } = useAccount();
  const { create, reset, step, isLoading, createdMarketId, error, balance } = useCreateMarket(address);
  const navigate = useNavigate();

  const halfLiquidity = (initialLiquidity / 2).toLocaleString('en-US', { minimumFractionDigits: 0 });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || initialLiquidity < 1) return;
    create(question.trim(), initialLiquidity, deadlineDays, category, resolutionSource.trim());
  }

  function handleGoToMarket() {
    if (createdMarketId !== null) navigate(`/market/${createdMarketId}`);
    onClose();
  }

  function handleClose() {
    reset();
    onClose();
  }

  const inputClass =
    'w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-slate-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none disabled:opacity-50 transition-colors';
  const labelClass = 'block text-sm font-medium text-slate-300 mb-1.5';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl bg-slate-900 border border-slate-700/50 p-6 mx-4 shadow-xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-slate-100">Create Market</h2>
          <button
            onClick={handleClose}
            className="text-slate-400 hover:text-slate-200 transition-colors text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {step === 'success' ? (
          /* ---- Success State ---- */
          <div className="space-y-4">
            <div className="rounded-lg bg-emerald-900/30 border border-emerald-700/50 p-4 text-center">
              <div className="text-emerald-300 font-medium text-base mb-1">Market Created Successfully</div>
              {createdMarketId !== null && (
                <div className="text-emerald-400/70 text-sm">Market #{createdMarketId}</div>
              )}
            </div>
            <div className="flex gap-2">
              {createdMarketId !== null && (
                <button
                  onClick={handleGoToMarket}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors"
                >
                  View Market
                </button>
              )}
              <button
                onClick={handleClose}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          /* ---- Form ---- */
          <form onSubmit={handleSubmit} className="space-y-4">
            {!isConnected && (
              <p className="text-xs text-amber-400 bg-amber-900/20 border border-amber-700/40 rounded-lg px-3 py-2">
                Connect your wallet to provide liquidity and create a market.
              </p>
            )}

            {/* Question */}
            <div>
              <label className={labelClass}>What do you want to predict?</label>
              <textarea
                placeholder="Will X happen by Y date?"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                rows={3}
                disabled={isLoading}
                className={`${inputClass} resize-none`}
                required
              />
            </div>

            {/* Category */}
            <div>
              <label className={labelClass}>Category</label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                disabled={isLoading}
                className={inputClass}
              >
                {CATEGORIES.map(c => (
                  <option key={c.toLowerCase()} value={c.toLowerCase()}>
                    {c}
                  </option>
                ))}
              </select>
            </div>

            {/* Resolution Source */}
            <div>
              <label className={labelClass}>Resolution Source</label>
              <input
                type="url"
                placeholder="Link to resolution source (e.g. Polymarket URL)"
                value={resolutionSource}
                onChange={e => setResolutionSource(e.target.value)}
                disabled={isLoading}
                className={inputClass}
              />
              <p className="text-xs text-slate-500 mt-1">Optional. Where the outcome will be verified.</p>
            </div>

            {/* Initial Liquidity */}
            <div>
              <label className={labelClass}>Initial Liquidity (USDC)</label>
              <input
                type="number"
                min={1}
                step={1}
                value={initialLiquidity}
                onChange={e => setInitialLiquidity(Number(e.target.value))}
                disabled={isLoading}
                className={inputClass}
              />
              <div className="flex items-center justify-between mt-1">
                <p className="text-xs text-slate-500">Minimum: 1 USDC</p>
                {balance !== undefined && (
                  <p className="text-xs text-slate-500">
                    Balance: {formatUSDC(balance)} USDC
                  </p>
                )}
              </div>
            </div>

            {/* Staking Info Card */}
            <div className="bg-blue-950/30 border border-blue-800/30 rounded-lg p-3 text-sm text-blue-300 space-y-1.5">
              <p>
                This amount seeds the AMM. It will be split 50/50 between YES and NO reserves.
              </p>
              {initialLiquidity > 0 && (
                <p className="text-blue-400/80 font-mono text-xs">
                  {initialLiquidity.toLocaleString()} USDC &rarr; {halfLiquidity} YES reserve + {halfLiquidity} NO reserve
                </p>
              )}
              <p className="text-blue-400/60 text-xs">
                Your initial liquidity is staked as AMM seed capital. You will receive trading fees proportional to your share.
              </p>
            </div>

            {/* Deadline */}
            <div>
              <label className={labelClass}>Deadline (days from now)</label>
              <input
                type="number"
                min={1}
                max={365}
                value={deadlineDays}
                onChange={e => setDeadlineDays(Number(e.target.value))}
                disabled={isLoading}
                className={inputClass}
              />
            </div>

            {/* Step Progress */}
            {isLoading && (
              <div className="space-y-2">
                <p className="text-xs text-blue-400 font-medium">{STEP_LABEL[step]}</p>
                <div className="flex items-center gap-2">
                  {[1, 2, 3].map(n => (
                    <div
                      key={n}
                      className={`h-1.5 flex-1 rounded-full transition-colors ${
                        STEP_NUMBER[step] !== undefined && n <= STEP_NUMBER[step]
                          ? 'bg-blue-500'
                          : 'bg-slate-700'
                      }`}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <p className="text-xs text-rose-400 bg-rose-900/20 border border-rose-700/30 rounded-lg px-3 py-2">
                {(error as Error).message.slice(0, 200)}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !isConnected || !question.trim() || initialLiquidity < 1}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Processing...' : 'Create Market'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
