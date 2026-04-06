import { useAccount } from 'wagmi';
import { useTokenBalance } from '../../hooks/useUserPositions';
import { useRedeem } from '../../hooks/useTrading';
import { formatTokens } from '../../lib/format';
import type { MarketFromAPI } from '../../types/market';

interface PositionDisplayProps {
  market: MarketFromAPI;
}

export default function PositionDisplay({ market }: PositionDisplayProps) {
  const { address } = useAccount();
  const { data: yesBalance } = useTokenBalance(market.yesToken as `0x${string}`, address);
  const { data: noBalance } = useTokenBalance(market.noToken as `0x${string}`, address);
  const { redeem, isPending, isConfirming, isSuccess, error } = useRedeem();

  const hasYes = yesBalance && (yesBalance as bigint) > 0n;
  const hasNo = noBalance && (noBalance as bigint) > 0n;

  if (!hasYes && !hasNo) return null;

  const canRedeem = market.resolved;
  const isWinner = market.resolved && (
    (market.outcome && hasYes) || (!market.outcome && hasNo)
  );

  return (
    <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
      <h3 className="text-sm font-medium text-slate-300 mb-3">Your Position</h3>

      <div className="space-y-2">
        {hasYes && (
          <div className="flex justify-between items-center text-sm">
            <span className="text-emerald-400">YES tokens</span>
            <span className="text-slate-200">{formatTokens(yesBalance as bigint)}</span>
          </div>
        )}
        {hasNo && (
          <div className="flex justify-between items-center text-sm">
            <span className="text-rose-400">NO tokens</span>
            <span className="text-slate-200">{formatTokens(noBalance as bigint)}</span>
          </div>
        )}
      </div>

      {canRedeem && isWinner && (
        <button
          onClick={() => redeem(market.id)}
          disabled={isPending || isConfirming}
          className="mt-4 w-full py-2.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
        >
          {isPending || isConfirming ? 'Claiming...' : 'Claim USDC'}
        </button>
      )}

      {isSuccess && (
        <p className="mt-2 text-xs text-emerald-400">Redeemed successfully!</p>
      )}
      {error && (
        <p className="mt-2 text-xs text-rose-400">{error.message?.slice(0, 100)}</p>
      )}
    </div>
  );
}
