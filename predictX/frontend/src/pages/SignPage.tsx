import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAccount, useConnect } from 'wagmi';
import { injected } from 'wagmi/connectors';
import { parseUnits, formatUnits } from 'viem';
import {
  useApproveUSDC,
  useAllowance,
  useBuyYes,
  useBuyNo,
  useSell,
  useRedeem,
} from '../hooks/useTrading';
import { useSubmitEvidence } from '../hooks/useEvidence';
import { USDC_DECIMALS } from '../config/contracts';

type Action = 'buyYes' | 'buyNo' | 'sell' | 'redeem' | 'submitEvidence';

const ACTION_LABELS: Record<Action, string> = {
  buyYes: 'Buy YES',
  buyNo: 'Buy NO',
  sell: 'Sell',
  redeem: 'Redeem',
  submitEvidence: 'Submit Evidence',
};

function parseParams(sp: URLSearchParams) {
  return {
    action: (sp.get('action') || '') as Action,
    marketId: Number(sp.get('marketId') ?? -1),
    amount: sp.get('amount') || '0',       // USDC (human-readable, e.g. "100")
    direction: sp.get('direction') || 'YES',
    ipfsHash: sp.get('ipfsHash') || '',
    summary: sp.get('summary') || '',
    tokenAmount: sp.get('tokenAmount') || '0',
    source: sp.get('source') || 'Agent',
  };
}

export default function SignPage() {
  const [searchParams] = useSearchParams();
  const params = parseParams(searchParams);
  const { address, isConnected } = useAccount();
  const { connect } = useConnect();

  const [step, setStep] = useState<'preview' | 'approving' | 'executing' | 'done' | 'error'>('preview');
  const [errorMsg, setErrorMsg] = useState('');

  // Hooks for each action
  const allowance = useAllowance(address);
  const approveUSDC = useApproveUSDC();
  const buyYes = useBuyYes();
  const buyNo = useBuyNo();
  const sell = useSell();
  const redeem = useRedeem();
  const evidence = useSubmitEvidence();

  const needsApproval =
    (params.action === 'buyYes' || params.action === 'buyNo') &&
    allowance.data !== undefined &&
    (allowance.data as bigint) < parseUnits(params.amount, USDC_DECIMALS);

  // Chain approval → execute
  useEffect(() => {
    if (step === 'approving' && approveUSDC.isSuccess) {
      setStep('executing');
      executeTrade();
    }
  }, [approveUSDC.isSuccess]);

  // Detect trade success
  const activeHook = getActiveHook();
  useEffect(() => {
    if (step === 'executing' && activeHook?.isSuccess) {
      setStep('done');
    }
  }, [activeHook?.isSuccess]);

  // Detect errors
  useEffect(() => {
    const err = approveUSDC.error || activeHook?.error;
    if (err && step !== 'done') {
      setErrorMsg(err.message?.slice(0, 200) || 'Transaction failed');
      setStep('error');
    }
  }, [approveUSDC.error, activeHook?.error]);

  function getActiveHook() {
    switch (params.action) {
      case 'buyYes': return buyYes;
      case 'buyNo': return buyNo;
      case 'sell': return sell;
      case 'redeem': return redeem;
      case 'submitEvidence': return evidence;
      default: return null;
    }
  }

  function executeTrade() {
    switch (params.action) {
      case 'buyYes':
        buyYes.buy(params.marketId, params.amount);
        break;
      case 'buyNo':
        buyNo.buy(params.marketId, params.amount);
        break;
      case 'sell':
        sell.sell(params.marketId, params.direction === 'YES', params.tokenAmount);
        break;
      case 'redeem':
        redeem.redeem(params.marketId);
        break;
      case 'submitEvidence':
        evidence.submit(
          params.marketId,
          params.summary.split(':')[0] || 'Agent Evidence',
          params.summary,
          '',
          params.direction,
        );
        break;
    }
  }

  function handleConfirm() {
    if (!isConnected) {
      connect({ connector: injected() });
      return;
    }
    if (needsApproval) {
      setStep('approving');
      approveUSDC.approve(params.amount);
    } else {
      setStep('executing');
      executeTrade();
    }
  }

  // Validate params
  if (!params.action || !ACTION_LABELS[params.action]) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16">
        <div className="rounded-xl bg-slate-800/50 border border-rose-700/50 p-8 text-center">
          <h1 className="text-xl font-bold text-rose-400 mb-2">Invalid Request</h1>
          <p className="text-sm text-slate-400">
            Missing or invalid <code className="text-slate-300">action</code> parameter.
            <br />
            Valid actions: {Object.keys(ACTION_LABELS).join(', ')}
          </p>
        </div>
      </div>
    );
  }

  const isBuy = params.action === 'buyYes' || params.action === 'buyNo';
  const isPending = step === 'approving' || step === 'executing';

  return (
    <div className="max-w-lg mx-auto px-4 py-16">
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-lg bg-blue-600/20 flex items-center justify-center text-blue-400 text-lg">
            {isBuy ? '$' : params.action === 'submitEvidence' ? 'E' : 'T'}
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-100">
              {ACTION_LABELS[params.action]}
            </h1>
            <p className="text-xs text-slate-500">
              Requested by {params.source}
            </p>
          </div>
        </div>

        {/* Transaction Summary */}
        <div className="space-y-3 mb-6">
          <SummaryRow label="Market" value={`#${params.marketId}`} />

          {isBuy && (
            <>
              <SummaryRow label="Direction" value={params.action === 'buyYes' ? 'YES' : 'NO'}
                className={params.action === 'buyYes' ? 'text-emerald-400' : 'text-rose-400'} />
              <SummaryRow label="Amount" value={`${params.amount} USDC`} />
            </>
          )}

          {params.action === 'sell' && (
            <>
              <SummaryRow label="Direction" value={params.direction}
                className={params.direction === 'YES' ? 'text-emerald-400' : 'text-rose-400'} />
              <SummaryRow label="Token Amount" value={params.tokenAmount} />
            </>
          )}

          {params.action === 'submitEvidence' && (
            <>
              <SummaryRow label="Direction" value={params.direction}
                className={params.direction === 'YES' ? 'text-emerald-400' : 'text-rose-400'} />
              <SummaryRow label="IPFS Hash" value={params.ipfsHash ? `${params.ipfsHash.slice(0, 10)}...${params.ipfsHash.slice(-6)}` : 'via backend'} />
              {params.summary && (
                <div className="p-3 rounded-lg bg-slate-900/50 text-xs text-slate-400">
                  {params.summary.slice(0, 200)}
                </div>
              )}
            </>
          )}

          {needsApproval && (
            <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-700/30 text-xs text-amber-400">
              Requires USDC approval before trading. Two MetaMask confirmations needed.
            </div>
          )}
        </div>

        {/* Action Button */}
        {step === 'preview' && (
          <button
            onClick={handleConfirm}
            className="w-full py-3 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
          >
            {!isConnected ? 'Connect Wallet & Sign' : needsApproval ? 'Approve & Execute' : 'Sign Transaction'}
          </button>
        )}

        {step === 'approving' && (
          <div className="text-center py-3">
            <div className="text-sm text-amber-400 animate-pulse">
              Step 1/2: Approve USDC... Confirm in MetaMask
            </div>
          </div>
        )}

        {step === 'executing' && (
          <div className="text-center py-3">
            <div className="text-sm text-blue-400 animate-pulse">
              {needsApproval ? 'Step 2/2: ' : ''}Executing... Confirm in MetaMask
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="text-center py-3">
            <div className="text-sm text-emerald-400 font-medium mb-2">
              Transaction successful!
            </div>
            <p className="text-xs text-slate-500">
              You can close this tab and return to your agent.
            </p>
          </div>
        )}

        {step === 'error' && (
          <div>
            <div className="p-3 rounded-lg bg-rose-900/20 border border-rose-700/30 text-xs text-rose-400 mb-3">
              {errorMsg}
            </div>
            <button
              onClick={() => { setStep('preview'); setErrorMsg(''); }}
              className="w-full py-2 rounded-lg text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
            >
              Try Again
            </button>
          </div>
        )}

        {/* Footer */}
        <p className="mt-6 text-xs text-slate-600 text-center">
          This transaction was prepared by an AI agent.
          <br />Review carefully before signing.
        </p>
      </div>
    </div>
  );
}

function SummaryRow({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-slate-700/30">
      <span className="text-sm text-slate-400">{label}</span>
      <span className={`text-sm font-medium ${className || 'text-slate-200'}`}>{value}</span>
    </div>
  );
}
