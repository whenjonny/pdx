/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CHAIN: string;
  readonly VITE_RPC_URL: string;
  readonly VITE_PDX_MARKET_ADDRESS: string;
  readonly VITE_MOCK_USDC_ADDRESS: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
