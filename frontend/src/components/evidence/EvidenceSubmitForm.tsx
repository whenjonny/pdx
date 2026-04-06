import { useState } from 'react';
import { useAccount } from 'wagmi';
import { useSubmitEvidence } from '../../hooks/useEvidence';

interface EvidenceSubmitFormProps {
  marketId: number;
}

export default function EvidenceSubmitForm({ marketId }: EvidenceSubmitFormProps) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const { address } = useAccount();
  const { submit, isUploading, uploadError, isPending, isConfirming, isSuccess, txError } = useSubmitEvidence();

  const isSubmitting = isUploading || isPending || isConfirming;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    submit(marketId, title, content, sourceUrl || undefined);
  }

  if (isSuccess) {
    return (
      <div className="p-4 rounded-lg bg-emerald-900/20 border border-emerald-800/30 text-emerald-400 text-sm">
        Evidence submitted! You now get 0.1% trading fees.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
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

      {(uploadError || txError) && (
        <p className="text-xs text-rose-400">
          {uploadError || txError?.message?.slice(0, 100)}
        </p>
      )}
    </form>
  );
}
