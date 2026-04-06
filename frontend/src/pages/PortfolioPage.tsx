import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAccount, useConnect } from 'wagmi';
import { useUserPositions, useUserTransactions, useUserSummary } from '../hooks/usePortfolio';
import { formatAddress } from '../lib/format';
import type { UserPosition, UserTransaction } from '../types/market';

function formatRelativeTime(timestamp: number): string {
  const now = Math.floor(Date.now() / 1000);
  const diff = now - timestamp;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(timestamp * 1000).toLocaleDateString();
}

function formatUsdcString(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) return '$0.00';
  return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatBalance(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) return '0.00';
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

const TX_TYPE_CONFIG: Record<UserTransaction['type'], { label: string; color: string }> = {
  buy_yes: { label: 'Buy YES', color: 'bg-emerald-500/20 text-emerald-400' },
  buy_no: { label: 'Buy NO', color: 'bg-rose-500/20 text-rose-400' },
  sell: { label: 'Sell', color: 'bg-amber-500/20 text-amber-400' },
  redeem: { label: 'Redeem', color: 'bg-blue-500/20 text-blue-400' },
  create_market: { label: 'Create Market', color: 'bg-purple-500/20 text-purple-400' },
  submit_evidence: { label: 'Evidence', color: 'bg-cyan-500/20 text-cyan-400' },
};

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4 flex-1 min-w-[140px]">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className="text-lg font-semibold text-slate-100">{value}</p>
    </div>
  );
}

function PositionsTable({ positions, isLoading }: { positions: UserPosition[] | undefined; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (!positions || positions.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <p className="text-lg mb-2">No active positions</p>
        <p className="text-sm">Start trading to build your portfolio.</p>
      </div>
    );
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/50 text-slate-400 text-left">
              <th className="pb-3 pr-4 font-medium">Market</th>
              <th className="pb-3 px-4 font-medium text-right">YES</th>
              <th className="pb-3 px-4 font-medium text-right">NO</th>
              <th className="pb-3 px-4 font-medium text-right">Value</th>
              <th className="pb-3 px-4 font-medium text-center">Status</th>
              <th className="pb-3 pl-4 font-medium text-center">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr
                key={pos.market_id}
                className="border-b border-slate-700/30 hover:bg-slate-800/30 transition-colors"
              >
                <td className="py-3 pr-4">
                  <Link
                    to={`/market/${pos.market_id}`}
                    className="text-slate-200 hover:text-blue-400 transition-colors line-clamp-2"
                  >
                    {pos.question}
                  </Link>
                </td>
                <td className="py-3 px-4 text-right text-emerald-400 font-mono">
                  {formatBalance(pos.yes_balance)}
                </td>
                <td className="py-3 px-4 text-right text-rose-400 font-mono">
                  {formatBalance(pos.no_balance)}
                </td>
                <td className="py-3 px-4 text-right text-slate-200 font-mono">
                  {formatUsdcString(pos.current_value_usdc)}
                </td>
                <td className="py-3 px-4 text-center">
                  {pos.market_resolved ? (
                    <span className="inline-block rounded-full px-2 py-0.5 text-xs bg-slate-600/50 text-slate-300">
                      Settled
                    </span>
                  ) : (
                    <span className="inline-block rounded-full px-2 py-0.5 text-xs bg-blue-500/20 text-blue-400">
                      Active
                    </span>
                  )}
                </td>
                <td className="py-3 pl-4 text-center">
                  {pos.market_resolved ? (
                    <OutcomeBadge position={pos} />
                  ) : (
                    <span className="text-slate-500">--</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {positions.map((pos) => (
          <div
            key={pos.market_id}
            className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4"
          >
            <Link
              to={`/market/${pos.market_id}`}
              className="text-sm text-slate-200 hover:text-blue-400 transition-colors font-medium line-clamp-2 mb-3 block"
            >
              {pos.question}
            </Link>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-slate-400">YES:</span>{' '}
                <span className="text-emerald-400 font-mono">{formatBalance(pos.yes_balance)}</span>
              </div>
              <div>
                <span className="text-slate-400">NO:</span>{' '}
                <span className="text-rose-400 font-mono">{formatBalance(pos.no_balance)}</span>
              </div>
              <div>
                <span className="text-slate-400">Value:</span>{' '}
                <span className="text-slate-200 font-mono">{formatUsdcString(pos.current_value_usdc)}</span>
              </div>
              <div>
                <span className="text-slate-400">Status:</span>{' '}
                {pos.market_resolved ? (
                  <span className="text-slate-300">Settled</span>
                ) : (
                  <span className="text-blue-400">Active</span>
                )}
              </div>
            </div>
            {pos.market_resolved && (
              <div className="mt-2 text-xs">
                <OutcomeBadge position={pos} />
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function OutcomeBadge({ position }: { position: UserPosition }) {
  const yesBalance = parseFloat(position.yes_balance);
  const noBalance = parseFloat(position.no_balance);
  const hadYes = yesBalance > 0;
  const hadNo = noBalance > 0;
  const won =
    (position.market_outcome && hadYes) || (!position.market_outcome && hadNo);

  if (!hadYes && !hadNo) {
    return <span className="text-slate-500">--</span>;
  }

  return won ? (
    <span className="inline-block rounded-full px-2 py-0.5 text-xs bg-emerald-500/20 text-emerald-400">
      Won
    </span>
  ) : (
    <span className="inline-block rounded-full px-2 py-0.5 text-xs bg-rose-500/20 text-rose-400">
      Lost
    </span>
  );
}

function HistoryTable({ transactions, isLoading }: { transactions: UserTransaction[] | undefined; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
      </div>
    );
  }

  if (!transactions || transactions.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <p className="text-lg mb-2">No transactions yet</p>
        <p className="text-sm">Your activity will appear here.</p>
      </div>
    );
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/50 text-slate-400 text-left">
              <th className="pb-3 pr-4 font-medium">Type</th>
              <th className="pb-3 px-4 font-medium">Market</th>
              <th className="pb-3 px-4 font-medium text-right">Amount</th>
              <th className="pb-3 px-4 font-medium">Tx Hash</th>
              <th className="pb-3 pl-4 font-medium text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx, i) => {
              const config = TX_TYPE_CONFIG[tx.type];
              const amount = tx.details.amount;
              return (
                <tr
                  key={`${tx.tx_hash}-${i}`}
                  className="border-b border-slate-700/30 hover:bg-slate-800/30 transition-colors"
                >
                  <td className="py-3 pr-4">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${config.color}`}>
                      {config.label}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <Link
                      to={`/market/${tx.market_id}`}
                      className="text-slate-300 hover:text-blue-400 transition-colors"
                    >
                      Market #{tx.market_id}
                    </Link>
                  </td>
                  <td className="py-3 px-4 text-right font-mono text-slate-200">
                    {amount != null ? String(amount) : '--'}
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-400 text-xs">
                    {formatAddress(tx.tx_hash)}
                  </td>
                  <td className="py-3 pl-4 text-right text-slate-400 text-xs">
                    {formatRelativeTime(tx.timestamp)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {transactions.map((tx, i) => {
          const config = TX_TYPE_CONFIG[tx.type];
          const amount = tx.details.amount;
          return (
            <div
              key={`${tx.tx_hash}-${i}`}
              className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${config.color}`}>
                  {config.label}
                </span>
                <span className="text-xs text-slate-400">{formatRelativeTime(tx.timestamp)}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <Link
                  to={`/market/${tx.market_id}`}
                  className="text-slate-300 hover:text-blue-400 transition-colors"
                >
                  Market #{tx.market_id}
                </Link>
                <span className="font-mono text-slate-200">
                  {amount != null ? String(amount) : '--'}
                </span>
              </div>
              <div className="mt-1 text-xs font-mono text-slate-500">
                {formatAddress(tx.tx_hash)}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

export default function PortfolioPage() {
  const [activeTab, setActiveTab] = useState<'positions' | 'history'>('positions');
  const { isConnected } = useAccount();
  const { connect, connectors } = useConnect();
  const { data: summary, isLoading: summaryLoading } = useUserSummary();
  const { data: positions, isLoading: positionsLoading } = useUserPositions();
  const { data: transactions, isLoading: transactionsLoading } = useUserTransactions();

  if (!isConnected) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-slate-100 mb-8">Portfolio</h1>
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-12 text-center">
          <p className="text-slate-400 mb-4">Connect your wallet to view your portfolio.</p>
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
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <h1 className="text-2xl font-bold text-slate-100 mb-6">Portfolio</h1>

      {/* Summary cards */}
      <div className="flex flex-wrap gap-3 mb-8">
        <SummaryCard
          label="Total Value"
          value={summaryLoading ? '...' : formatUsdcString(summary?.total_value_usdc ?? '0')}
        />
        <SummaryCard
          label="Active Positions"
          value={summaryLoading ? '...' : (summary?.active_positions ?? 0)}
        />
        <SummaryCard
          label="Markets Created"
          value={summaryLoading ? '...' : (summary?.markets_created ?? 0)}
        />
        <SummaryCard
          label="Evidence Submitted"
          value={summaryLoading ? '...' : (summary?.evidence_submitted ?? 0)}
        />
      </div>

      {/* Tab navigation */}
      <div className="flex gap-1 mb-6 border-b border-slate-700/50">
        <button
          onClick={() => setActiveTab('positions')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === 'positions'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-300'
          }`}
        >
          Positions
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === 'history'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-300'
          }`}
        >
          History
        </button>
      </div>

      {/* Tab content */}
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-4 md:p-6">
        {activeTab === 'positions' ? (
          <PositionsTable positions={positions} isLoading={positionsLoading} />
        ) : (
          <HistoryTable transactions={transactions} isLoading={transactionsLoading} />
        )}
      </div>
    </div>
  );
}
