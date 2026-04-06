import { useQuery } from '@tanstack/react-query';
import { useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { fetchEvidence, uploadEvidence } from '../lib/api';
import { PDX_MARKET_ADDRESS, PDX_MARKET_ABI } from '../config/contracts';
import { useState } from 'react';

export function useEvidenceList(marketId: number) {
  return useQuery({
    queryKey: ['evidence', marketId],
    queryFn: () => fetchEvidence(marketId),
    refetchInterval: 10_000,
    enabled: marketId >= 0,
  });
}

export function useSubmitEvidence() {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const { writeContract, data: hash, isPending, error: txError } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  async function submit(marketId: number, title: string, content: string, sourceUrl?: string) {
    setIsUploading(true);
    setUploadError(null);
    try {
      const result = await uploadEvidence({ market_id: marketId, title, content, source_url: sourceUrl });
      const ipfsHashBytes = `0x${result.ipfs_hash.replace(/^0x/, '')}` as `0x${string}`;
      writeContract({
        address: PDX_MARKET_ADDRESS,
        abi: PDX_MARKET_ABI,
        functionName: 'submitEvidence',
        args: [BigInt(marketId), ipfsHashBytes, `${title}: ${content.slice(0, 100)}`],
      });
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  }

  return { submit, isUploading, uploadError, isPending, isConfirming, isSuccess, txError };
}
