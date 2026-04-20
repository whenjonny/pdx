import { useAccount, useConnect, useDisconnect } from 'wagmi';
import { useUSDCBalance } from '../../hooks/useMockUSDC';
import { formatUSDC, formatAddress } from '../../lib/format';
import { Link } from 'react-router-dom';

export default function Header() {
  const { address, isConnected } = useAccount();
  const { connect, connectors } = useConnect();
  const { disconnect } = useDisconnect();
  const { data: balance } = useUSDCBalance(address);

  return (
    <header className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link to="/" className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
            PDX
          </Link>
          <nav className="flex gap-4 text-sm">
            <Link to="/" className="text-slate-300 hover:text-white transition-colors">Markets</Link>
            <Link to="/portfolio" className="text-slate-300 hover:text-white transition-colors">Portfolio</Link>
            <Link to="/faucet" className="text-slate-300 hover:text-white transition-colors">Faucet</Link>
            <Link to="/oracle" className="text-slate-300 hover:text-white transition-colors">Oracle</Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {isConnected && balance !== undefined && (
            <span className="text-sm text-slate-400">
              {formatUSDC(balance as bigint)} USDC
            </span>
          )}
          {isConnected ? (
            <button
              onClick={() => disconnect()}
              className="px-3 py-1.5 text-sm rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
            >
              {formatAddress(address!)}
            </button>
          ) : (
            <button
              onClick={() => connect({ connector: connectors[0] })}
              className="px-4 py-1.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 transition-colors font-medium"
            >
              Connect Wallet
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
