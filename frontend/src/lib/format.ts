import { USDC_DECIMALS } from '../config/contracts';

export function formatUSDC(amount: bigint): string {
  const num = Number(amount) / 10 ** USDC_DECIMALS;
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function parseUSDC(amount: string): bigint {
  const num = parseFloat(amount);
  if (isNaN(num) || num < 0) return 0n;
  return BigInt(Math.floor(num * 10 ** USDC_DECIMALS));
}

export function formatTokens(amount: bigint): string {
  const num = Number(amount) / 10 ** 6;
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatAddress(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function formatCountdown(deadline: number): string {
  const now = Math.floor(Date.now() / 1000);
  const diff = deadline - now;
  if (diff <= 0) return 'Expired';
  const days = Math.floor(diff / 86400);
  const hours = Math.floor((diff % 86400) / 3600);
  const mins = Math.floor((diff % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export function isLocked(lockTime: number): boolean {
  return Math.floor(Date.now() / 1000) >= lockTime;
}
