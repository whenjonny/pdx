import { useAccount } from 'wagmi';
import { useMintUSDC, useUSDCBalance } from '../hooks/useMockUSDC';
import { formatUSDC } from '../lib/format';

export default function FaucetPage() {
  const { address, isConnected } = useAccount();
  const { data: balance } = useUSDCBalance(address);
  const { mint, isPending, isConfirming, isSuccess, error } = useMintUSDC();

  function handleMint() {
    if (!address) return;
    mint(address, '10000');
  }

  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-8 text-center">
        <h1 className="text-xl font-bold text-slate-100 mb-2">MockUSDC Faucet</h1>
        <p className="text-sm text-slate-400 mb-6">
          Mint test USDC for trading on prediction markets
        </p>

        {balance !== undefined && (
          <div className="mb-6 p-4 rounded-lg bg-slate-900/50">
            <div className="text-xs text-slate-500 mb-1">Your Balance</div>
            <div className="text-2xl font-bold text-slate-100">
              {formatUSDC(balance as bigint)} <span className="text-sm text-slate-400">USDC</span>
            </div>
          </div>
        )}

        <button
          onClick={handleMint}
          disabled={!isConnected || isPending || isConfirming}
          className="w-full py-3 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {!isConnected
            ? 'Connect Wallet First'
            : isPending || isConfirming
              ? 'Minting...'
              : 'Mint 10,000 USDC'}
        </button>

        {isSuccess && (
          <p className="mt-3 text-sm text-emerald-400">
            10,000 USDC minted successfully!
          </p>
        )}
        {error && (
          <p className="mt-3 text-sm text-rose-400">
            {error.message?.slice(0, 100)}
          </p>
        )}

        <p className="mt-6 text-xs text-slate-600">
          MockUSDC is a test token with no real value.
          You can mint as many times as you need.
        </p>
      </div>
    </div>
  );
}
