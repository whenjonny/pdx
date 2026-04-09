import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAccount, useConnect, useReadContract, useWriteContract, useWaitForTransactionReceipt, useBlock } from 'wagmi';
import { useMarkets } from '../hooks/useMarkets';
import { formatUSDC } from '../lib/format';
import { PDX_MARKET_ADDRESS, PDX_MARKET_ABI } from '../config/contracts';
import pdxOracleAbi from '../../../contracts/abi/PDXOracle.json';

const PDX_ORACLE_ADDRESS = (import.meta.env.VITE_PDX_ORACLE_ADDRESS || '') as `0x${string}`;

export default function OraclePage() {
  const { address, isConnected } = useAccount();
  const { connect, connectors } = useConnect();
  const { data: markets, isLoading } = useMarkets();

  // Read oracle address from market contract
  const { data: oracleAddress } = useReadContract({
    address: PDX_MARKET_ADDRESS,
    abi: PDX_MARKET_ABI,
    functionName: 'oracle',
  });

  // Read oracle owner
  const { data: oracleOwner } = useReadContract({
    address: PDX_ORACLE_ADDRESS || undefined,
    abi: pdxOracleAbi as readonly unknown[],
    functionName: 'owner',
    query: { enabled: !!PDX_ORACLE_ADDRESS },
  });

  const isOracle = address && oracleOwner &&
    (address.toLowerCase() === (oracleOwner as string).toLowerCase());

  // Use on-chain block timestamp so time-warped local chains work correctly
  const { data: latestBlock } = useBlock();
  const now = latestBlock ? Number(latestBlock.timestamp) : Math.floor(Date.now() / 1000);

  const pendingMarkets = (markets ?? []).filter(
    m => !m.resolved && m.deadline <= now
  );
  const activeMarkets = (markets ?? []).filter(
    m => !m.resolved && m.deadline > now
  );
  const settledMarkets = (markets ?? []).filter(m => m.resolved);

  if (!isConnected) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-slate-100 mb-8">Oracle Admin</h1>
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-12 text-center">
          <p className="text-slate-400 mb-4">Connect the oracle wallet to manage settlements.</p>
          <button
            onClick={() => connect({ connector: connectors[0] })}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors"
          >
            Connect Wallet
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-100">Oracle Admin</h1>
        {isOracle ? (
          <span className="px-3 py-1 rounded-full text-xs font-medium bg-emerald-900/50 text-emerald-400 border border-emerald-700/40">
            Oracle Connected
          </span>
        ) : (
          <span className="px-3 py-1 rounded-full text-xs font-medium bg-amber-900/50 text-amber-400 border border-amber-700/40">
            Not Oracle
          </span>
        )}
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="rounded-xl bg-amber-900/20 border border-amber-800/30 p-4 text-center">
          <div className="text-2xl font-bold text-amber-400">{pendingMarkets.length}</div>
          <div className="text-xs text-amber-400/70 mt-1">Pending Settlement</div>
        </div>
        <div className="rounded-xl bg-blue-900/20 border border-blue-800/30 p-4 text-center">
          <div className="text-2xl font-bold text-blue-400">{activeMarkets.length}</div>
          <div className="text-xs text-blue-400/70 mt-1">Active</div>
        </div>
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4 text-center">
          <div className="text-2xl font-bold text-slate-300">{settledMarkets.length}</div>
          <div className="text-xs text-slate-500 mt-1">Settled</div>
        </div>
      </div>

      {!isOracle && (
        <div className="mb-6 rounded-xl bg-amber-900/20 border border-amber-700/40 p-4 text-sm text-amber-300">
          Your wallet is not the oracle owner. Settlement transactions will fail.
          {oracleOwner ? (
            <span className="block mt-1 text-xs text-amber-400/70 font-mono">
              Oracle owner: {String(oracleOwner)}
            </span>
          ) : null}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
        </div>
      ) : (
        <>
          {/* Pending Settlement */}
          {pendingMarkets.length > 0 && (
            <Section title="Pending Settlement" badge={pendingMarkets.length} badgeColor="text-amber-400 bg-amber-900/50">
              {pendingMarkets.map(m => (
                <SettleRow
                  key={m.id}
                  marketId={m.id}
                  question={m.question}
                  deadline={m.deadline}
                  volume={m.totalDeposited}
                  priceYes={m.priceYes}
                  disabled={!isOracle}
                  oracleAddress={PDX_ORACLE_ADDRESS}
                />
              ))}
            </Section>
          )}

          {pendingMarkets.length === 0 && (
            <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-8 text-center mb-6">
              <p className="text-slate-400">No markets pending settlement.</p>
              <p className="text-xs text-slate-500 mt-1">Markets become settleable after their deadline passes.</p>
            </div>
          )}

          {/* Active Markets (upcoming) */}
          {activeMarkets.length > 0 && (
            <Section title="Active Markets" badge={activeMarkets.length} badgeColor="text-blue-400 bg-blue-900/50">
              {activeMarkets.map(m => {
                const daysLeft = Math.max(0, Math.ceil((m.deadline - now) / 86400));
                return (
                  <div key={m.id} className="flex items-center justify-between py-3 border-b border-slate-700/30 last:border-0">
                    <div className="min-w-0 flex-1">
                      <Link to={`/market/${m.id}`} className="text-sm text-slate-200 hover:text-blue-400 transition-colors line-clamp-1">
                        #{m.id} {m.question}
                      </Link>
                    </div>
                    <span className="text-xs text-slate-500 ml-4 shrink-0">{daysLeft}d left</span>
                  </div>
                );
              })}
            </Section>
          )}

          {/* Settled Markets */}
          {settledMarkets.length > 0 && (
            <Section title="Settled" badge={settledMarkets.length} badgeColor="text-slate-400 bg-slate-700/50">
              {settledMarkets.map(m => (
                <div key={m.id} className="flex items-center justify-between py-3 border-b border-slate-700/30 last:border-0">
                  <div className="min-w-0 flex-1">
                    <Link to={`/market/${m.id}`} className="text-sm text-slate-400 hover:text-blue-400 transition-colors line-clamp-1">
                      #{m.id} {m.question}
                    </Link>
                  </div>
                  <span className={`text-xs font-medium ml-4 shrink-0 ${m.outcome ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {m.outcome ? 'YES' : 'NO'}
                  </span>
                </div>
              ))}
            </Section>
          )}
        </>
      )}

      {/* Oracle info */}
      <div className="mt-8 rounded-xl bg-slate-800/30 border border-slate-700/30 p-4 text-xs text-slate-500 space-y-1">
        <p>Oracle contract: <span className="font-mono text-slate-400">{PDX_ORACLE_ADDRESS || String(oracleAddress ?? 'N/A')}</span></p>
        <p>Oracle owner: <span className="font-mono text-slate-400">{String(oracleOwner ?? 'N/A')}</span></p>
        <p>Market contract: <span className="font-mono text-slate-400">{PDX_MARKET_ADDRESS}</span></p>
      </div>
    </div>
  );
}

function Section({ title, badge, badgeColor, children }: {
  title: string;
  badge: number;
  badgeColor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-sm font-medium text-slate-300">{title}</h2>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badgeColor}`}>{badge}</span>
      </div>
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4">
        {children}
      </div>
    </div>
  );
}

function SettleRow({ marketId, question, deadline, volume, priceYes, disabled, oracleAddress }: {
  marketId: number;
  question: string;
  deadline: number;
  volume: string;
  priceYes: number;
  disabled: boolean;
  oracleAddress: `0x${string}`;
}) {
  const [outcome, setOutcome] = useState<boolean | null>(null);

  const { writeContract, data: hash, isPending, error, reset } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  function settle() {
    if (outcome === null) return;

    // Call oracle.settleMarket if oracle address is available, otherwise call market.settle directly
    if (oracleAddress) {
      writeContract({
        address: oracleAddress,
        abi: pdxOracleAbi as readonly unknown[],
        functionName: 'settleMarket',
        args: [BigInt(marketId), outcome],
      });
    } else {
      writeContract({
        address: PDX_MARKET_ADDRESS,
        abi: PDX_MARKET_ABI,
        functionName: 'settle',
        args: [BigInt(marketId), outcome],
      });
    }
  }

  const overdue = Math.floor((Date.now() / 1000 - deadline) / 86400);
  const yesP = Math.round(priceYes * 100);

  return (
    <div className="py-4 border-b border-slate-700/30 last:border-0">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0 flex-1">
          <Link to={`/market/${marketId}`} className="text-sm text-slate-200 hover:text-blue-400 transition-colors">
            #{marketId} {question}
          </Link>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
            <span>Overdue: {overdue}d</span>
            <span>Vol: ${formatUSDC(BigInt(volume || '0'))}</span>
            <span>YES: {yesP}%</span>
          </div>
        </div>
      </div>

      {isSuccess ? (
        <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-900/20 border border-emerald-700/30 rounded-lg px-3 py-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5" /></svg>
          Settled as {outcome ? 'YES' : 'NO'}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={() => { reset(); setOutcome(true); }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              outcome === true
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-emerald-900/50 hover:text-emerald-400'
            }`}
          >
            YES
          </button>
          <button
            onClick={() => { reset(); setOutcome(false); }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              outcome === false
                ? 'bg-rose-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-rose-900/50 hover:text-rose-400'
            }`}
          >
            NO
          </button>
          <button
            onClick={settle}
            disabled={outcome === null || isPending || isConfirming || disabled}
            className="ml-2 px-4 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 text-white hover:bg-indigo-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isPending ? 'Signing...' : isConfirming ? 'Confirming...' : 'Settle'}
          </button>
        </div>
      )}

      {error && (
        <p className="mt-2 text-xs text-rose-400 bg-rose-900/20 border border-rose-700/30 rounded-lg px-3 py-2">
          {(error as Error).message.slice(0, 150)}
        </p>
      )}
    </div>
  );
}
