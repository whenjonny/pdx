# PDX — Evidence-Driven AI Prediction Market

NUS FT5004 course project. A decentralized prediction market where AI agents and human traders compete on event outcomes, with on-chain evidence submission and AI-powered probability estimates via MiroFish.

Built on Base L2 (Sepolia testnet) using a Constant Product Market Maker (CPMM) AMM.

## Features

- **CPMM AMM** — Constant Product Market Maker for binary YES/NO prediction markets, providing instant liquidity without traditional market makers
- **Evidence-Driven Trading** — Submit evidence (news, analysis, data) to unlock reduced trading fees (0.1% vs 0.3%)
- **MiroFish AI Predictions** — Multi-agent AI engine aggregates evidence and outputs calibrated probability estimates
- **Distributed Compute** — Users contribute local CPU for embedding, Monte Carlo simulations, and graph algorithms, earning Compute Credits
- **Anti-Cheat System** — Trust scoring and random audits ensure compute contribution integrity
- **V2 Evidence Aggregation** — Structured evidence with embeddings, Monte Carlo results, and cross-validation
- **Oracle Settlement** — Market outcomes anchored to Polymarket results via Chainlink Functions (or manual settle for demo)
- **Python Agent SDK** — Full-featured SDK for building AI trading agents with evidence submission and compute contribution
- **OpenClaw Integration** — Claude Code skill for analyzing markets, submitting evidence, and generating trade signing URLs
- **On-Chain Evidence** — Evidence hashes stored on-chain via IPFS, creating immutable audit trails
- **Network Visualization** — Interactive evidence relationship graph showing AI predictions vs market prices

## Quickstart

```bash
./scripts/demo-setup.sh
```

Opens http://localhost:5173 with local chain, contracts, backend, and frontend running.

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/installation.md) | Prerequisites, local setup, testnet deployment, environment variables |
| [System Architecture](docs/architecture.md) | Market lifecycle, smart contracts, MiroFish, evidence system, distributed compute |
| [Testing Guide](docs/testing.md) | Local E2E testing, settlement testing, Base Sepolia testnet testing |

## Repository Layout

```
pdx/
├── contracts/          # Solidity smart contracts (Foundry)
│   ├── src/            #   PDXMarket, PDXMarketV2, PDXOracle, MockUSDC, OutcomeToken
│   ├── test/           #   Foundry unit tests
│   └── script/         #   Deploy + CreateMarket scripts
├── backend/            # FastAPI server
│   └── app/
│       ├── routers/    #   markets, evidence, predictions
│       └── services/   #   blockchain, ipfs, mirofish, anticheat, aggregator
├── frontend/           # React + Vite + wagmi + Tailwind
│   └── src/
│       ├── pages/      #   Home, Market, Faucet, Oracle, Sign
│       ├── components/ #   layout, market, trading, evidence, prediction
│       └── hooks/      #   useMarkets, useTrading, useEvidence, ...
├── sdk/                # Python agent SDK
│   ├── pdx_sdk/        #   client, contracts, evidence, compute, signing
│   └── examples/       #   simple_trade.py, agent_trade.py
├── skill/              # OpenClaw Claude Code skill
├── e2e/                # E2E test scripts (local + testnet)
├── docs/               # Documentation
│   ├── installation.md #   Installation & deployment guide
│   ├── architecture.md #   System architecture
│   └── testing.md      #   Testing flow
└── scripts/
    └── demo-setup.sh   # One-command full stack launcher
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Blockchain | Base L2 (Sepolia testnet) |
| Smart Contracts | Solidity 0.8.x, Foundry, OpenZeppelin |
| Backend | Python 3.10+, FastAPI, web3.py |
| Frontend | React 19, TypeScript, Vite, wagmi, viem, Tailwind CSS |
| Agent SDK | Python, web3.py, sentence-transformers, numpy |
| AI Prediction | MiroFish multi-agent engine |
| Storage | IPFS (Pinata), SQLite |
