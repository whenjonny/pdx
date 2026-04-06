import { useState, useEffect } from 'react';
import { useAccount } from 'wagmi';
import { useSubmitEvidence, useHasEvidence } from '../../hooks/useEvidence';

interface EvidenceSubmitFormProps {
  marketId: number;
}

export default function EvidenceSubmitForm({ marketId }: EvidenceSubmitFormProps) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [direction, setDirection] = useState<'YES' | 'NO'>('YES');
  const [showSuccess, setShowSuccess] = useState(false);
  const { address } = useAccount();
  const { submit, isUploading, uploadError, isPending, isConfirming, isSuccess, txError } = useSubmitEvidence();
  const { data: hasEvidence, refetch: refetchHasEvidence } = useHasEvidence(marketId, address);

  const isSubmitting = isUploading || isPending || isConfirming;

  useEffect(() => {
    if (isSuccess) {
      setShowSuccess(true);
      setTitle('');
      setContent('');
      setSourceUrl('');
      setDirection('YES');
      refetchHasEvidence();
      const timer = setTimeout(() => setShowSuccess(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isSuccess]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    submit(marketId, title, content, sourceUrl || undefined, direction);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setDirection('YES')}
          className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            direction === 'YES'
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          YES
        </button>
        <button
          type="button"
          onClick={() => setDirection('NO')}
          className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            direction === 'NO'
              ? 'bg-rose-600 text-white'
              : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          NO
        </button>
      </div>
      <input
        type="text"
        placeholder="Evidence title"
        value={title}
        onChange={e => setTitle(e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
      />
      <textarea
        placeholder="Describe your evidence..."
        value={content}
        onChange={e => setContent(e.target.value)}
        rows={3}
        className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-blue-500 resize-none"
      />
      <input
        type="url"
        placeholder="Source URL (optional)"
        value={sourceUrl}
        onChange={e => setSourceUrl(e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
      />

      <button
        type="submit"
        disabled={isSubmitting || !address || !title.trim() || !content.trim()}
        className="w-full py-2 rounded-lg text-sm font-medium bg-purple-600 text-white hover:bg-purple-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isSubmitting ? 'Submitting...' : 'Submit Evidence'}
      </button>

      {showSuccess && (
        <p className="text-xs text-emerald-400">Evidence submitted successfully!</p>
      )}
      {!showSuccess && (hasEvidence as boolean) && (
        <p className="text-xs text-emerald-400">Evidence Submitted - Trading fee reduced to 0.1%</p>
      )}
      {(uploadError || txError) && (
        <p className="text-xs text-rose-400">
          {uploadError || txError?.message?.slice(0, 100)}
        </p>
      )}
    </form>
  );
}
