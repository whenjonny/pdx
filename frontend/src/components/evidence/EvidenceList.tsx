import { useEvidenceList } from '../../hooks/useEvidence';
import { formatAddress } from '../../lib/format';

interface EvidenceListProps {
  marketId: number;
}

export default function EvidenceList({ marketId }: EvidenceListProps) {
  const { data: evidence, isLoading } = useEvidenceList(marketId);

  if (isLoading) return <div className="animate-pulse h-20 bg-slate-800 rounded-lg" />;

  if (!evidence?.length) {
    return (
      <div className="text-sm text-slate-500 text-center py-6">
        No evidence submitted yet
      </div>
    );
  }

  return (
    <div className="space-y-3 pr-1" style={{ maxHeight: '190px', overflowY: 'auto' }}>
      {evidence.map((e, i) => (
        <div key={i} className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/30">
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span>{formatAddress(e.submitter)}</span>
            <span>{new Date(e.timestamp * 1000).toLocaleDateString()}</span>
          </div>
          <p className="text-sm text-slate-300">{e.summary}</p>
        </div>
      ))}
    </div>
  );
}
