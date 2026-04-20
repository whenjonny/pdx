import pdxMarketAbi from '../../../contracts/abi/PDXMarket.json';
import mockUsdcAbi from '../../../contracts/abi/MockUSDC.json';
import outcomeTokenAbi from '../../../contracts/abi/OutcomeToken.json';

export const PDX_MARKET_ADDRESS = (import.meta.env.VITE_PDX_MARKET_ADDRESS || '') as `0x${string}`;
export const MOCK_USDC_ADDRESS = (import.meta.env.VITE_MOCK_USDC_ADDRESS || '') as `0x${string}`;

export const PDX_MARKET_ABI = pdxMarketAbi as readonly unknown[];
export const MOCK_USDC_ABI = mockUsdcAbi as readonly unknown[];
export const OUTCOME_TOKEN_ABI = outcomeTokenAbi as readonly unknown[];

export const USDC_DECIMALS = 6;
export const TOKEN_DECIMALS = 6;
