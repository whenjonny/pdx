# PDX Credibility Sources

Reference document for the credibility scoring system used in prediction market evidence evaluation.

## Tier 1: High Credibility (8-10)

| Source | Score | Domain |
|--------|-------|--------|
| Nature | 10 | Science |
| Science (AAAS) | 10 | Science |
| The Lancet | 10 | Medicine |
| NEJM | 10 | Medicine |
| IEEE | 9 | Technology |
| ACM | 9 | Computer Science |
| Reuters | 9 | News |
| Associated Press | 9 | News |
| WHO | 9 | Health |
| CDC | 9 | Health |
| World Bank | 9 | Economics |
| IMF | 9 | Economics |
| Federal Reserve | 9 | Monetary Policy |
| SEC | 9 | Financial Regulation |
| CoinDesk Research | 8 | Crypto |
| Glassnode | 8 | Crypto On-Chain |
| arXiv | 8 | Preprints |
| SSRN | 8 | Social Science |
| BBC | 8 | News |
| Wall Street Journal | 8 | Finance/News |
| Financial Times | 8 | Finance |
| Bloomberg | 8 | Finance |
| Chainalysis | 8 | Crypto Analytics |

## Tier 2: Moderate Credibility (5-7)

| Source | Score | Domain |
|--------|-------|--------|
| Wikipedia | 7 | General |
| New York Times | 7 | News |
| The Guardian | 7 | News |
| Economist | 7 | Economics |
| CoinGecko | 7 | Crypto Data |
| CoinMarketCap | 7 | Crypto Data |
| Dune Analytics | 7 | On-Chain Data |
| DefiLlama | 7 | DeFi Data |
| Etherscan | 7 | Blockchain Explorer |
| TechCrunch | 6 | Technology |
| Ars Technica | 6 | Technology |
| The Block | 6 | Crypto News |
| Decrypt | 6 | Crypto News |
| CNBC | 6 | Finance |
| Forbes | 6 | Business |
| Polymarket | 6 | Prediction Markets |
| Metaculus | 6 | Prediction/Forecasting |
| GitHub | 5 | Technology |
| Stack Overflow | 5 | Technology |

## Tier 3: Lower Credibility (1-4)

| Source | Score | Domain |
|--------|-------|--------|
| Reddit | 4 | Social |
| Crypto Twitter/X | 3 | Social/Crypto |
| YouTube | 3 | Video |
| Medium | 3 | Blog |
| Substack | 3 | Blog |
| Mirror.xyz | 3 | Web3 Blog |
| Telegram Groups | 2 | Social |
| Discord Servers | 2 | Social |
| Facebook | 2 | Social |
| TikTok | 1 | Social |
| Unknown/Other | 3 | Default |

## Scoring Methodology

The credibility score feeds into the MiroFish V2 aggregation as a weight multiplier:

- `weight = confidence * (credibility / 10) * recency`
- Sources not in the database default to score 3
- Subdomain matching: `news.bbc.co.uk` matches `bbc.co.uk`
- Multiple high-credibility sources on the same claim increase overall confidence

## For Prediction Markets Specifically

When evaluating evidence for prediction markets, prioritize:

1. **Primary data sources** over commentary (e.g. Fed minutes > CNBC analyst opinion)
2. **Quantitative data** over qualitative (e.g. on-chain metrics > "market sentiment")
3. **Recent information** over historical (recency decay factor applies)
4. **Official announcements** over speculation
5. **Consensus among independent sources** over single-source claims
