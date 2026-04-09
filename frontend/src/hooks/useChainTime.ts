import { useBlock } from 'wagmi';

/**
 * Returns the latest block timestamp (seconds).
 * Falls back to Date.now() if the block hasn't loaded yet.
 * This ensures time-warped local chains (anvil_setNextBlockTimestamp) work correctly.
 */
export function useChainTime(): number {
  const { data: block } = useBlock();
  return block ? Number(block.timestamp) : Math.floor(Date.now() / 1000);
}
