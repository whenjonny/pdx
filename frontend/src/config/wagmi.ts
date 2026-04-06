import { http, createConfig } from 'wagmi';
import { baseSepolia, hardhat } from 'wagmi/chains';
import { injected } from 'wagmi/connectors';

const isLocal = import.meta.env.VITE_CHAIN === 'local';

export const config = createConfig({
  chains: isLocal ? [hardhat] : [baseSepolia],
  connectors: [injected()],
  transports: isLocal
    ? { [hardhat.id]: http('http://localhost:8545') }
    : { [baseSepolia.id]: http(import.meta.env.VITE_RPC_URL || 'https://sepolia.base.org') },
});

export const targetChain = isLocal ? hardhat : baseSepolia;
