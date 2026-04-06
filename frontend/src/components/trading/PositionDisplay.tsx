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

  const yesAmt = (yesBalance as bigint) ?? 0n;
  const noAmt = (noBalance as bigint) ?? 0n;
  const hasYes = yesAmt > 0n;
  const hasNo = noAmt > 0n;

  // After successful redeem and balances have updated to 0
  if (!hasYes && !hasNo) {
    if (isSuccess) {
      return (
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
          <h3 className="text-sm font-medium text-slate-300 mb-3">Your Position</h3>
          <p className="text-sm text-emerald-400">All Redeemed</p>
        </div>
      );
    }
    return null;
  }

  const redeemableAmt = market.resolved
    ? (market.outcome ? yesAmt : noAmt)
    : 0n;
  const hasRedeemable = redeemableAmt > 0n;

  return (
    <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5">
      <h3 className="text-sm font-medium text-slate-300 mb-3">Your Position</h3>

      <div className="space-y-2">
        {hasYes && (
          <div className="flex justify-between items-center text-sm">
            <span className="text-emerald-400">YES</span>
            <span className="text-slate-200">{formatTokens(yesAmt)} tokens</span>
          </div>
        )}
        {hasNo && (
          <div className="flex justify-between items-center text-sm">
            <span className="text-rose-400">NO</span>
            <span className="text-slate-200">{formatTokens(noAmt)} tokens</span>
          </div>
        )}
      </div>

      {market.resolved && (
        <div className="mt-3 pt-3 border-t border-slate-700/50">
          {hasRedeemable ? (
            <>
              <div className="flex justify-between items-center text-sm mb-3">
                <span className="text-slate-400">Redeemable</span>
                <span className="text-emerald-300 font-medium">{formatTokens(redeemableAmt)} USDC</span>
              </div>
              <button
                onClick={() => redeem(market.id)}
                disabled={isPending || isConfirming}
                className="w-full py-2.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
              >
                {isPending || isConfirming ? 'Claiming...' : 'Claim USDC'}
              </button>
            </>
          ) : (
            <p className="text-sm text-slate-500">
              {market.outcome ? 'NO' : 'YES'} tokens are not redeemable — market resolved {market.outcome ? 'YES' : 'NO'}.
            </p>
          )}
        </div>
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
