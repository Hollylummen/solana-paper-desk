# Solana Paper Trading Desk (starter)

A paper-trading-first starter project for a Solana memecoin monitoring desk. It includes a Streamlit dashboard, a market-data adapter for DEX Screener, six separated agent modules, a SQLite audit log, position sizing, simulated entries/exits, and a daily recap.

## Important scope and safety limits

- **Paper trading only.** There is no wallet signing, no private-key handling, and no live order execution in this project.
- Market data is not a security audit. DEX Screener does not provide every field required by the requested rules (mint/freeze authority, LP lock/burn proof, top-holder concentration, or developer-wallet rug history). The filter therefore **fails closed** when these checks are not verified; it will not open paper positions from live data until a real, independently verified security adapter is added.
- The included `demo` mode uses synthetic data only to test the workflow and dashboard. Demo results are not market results and do not predict returns.
- A paper stop-loss is only a simulation. Real tokens can gap, lose liquidity, or become impossible to sell.
- The 8% position cap is a cap on portfolio balance allocated to one simulated position, not a guarantee of only 8% loss. An 8% position with a 6% stop implies roughly 0.48% of portfolio equity at the stop before fees/slippage, but execution can be worse.
- No profitability is promised. This is software scaffolding for testing, not investment advice.

## Quick start (Mac / Windows)

1. Install Python 3.11 or newer from https://www.python.org/downloads/
2. Unzip this folder.
3. Open Terminal (Mac) or PowerShell (Windows), then `cd` into the `solana_paper_desk` folder.
4. Create a virtual environment:
   - Mac: `python3 -m venv .venv && source .venv/bin/activate`
   - Windows: `py -m venv .venv; .venv\\Scripts\\Activate.ps1`
5. Install packages: `pip install -r requirements.txt`
6. Start dashboard: `streamlit run app.py`
7. In the sidebar choose **Demo data** to test the dashboard, or **Live market discovery** to read public DEX Screener data. Live market mode is monitoring only and will fail closed on unverified token security checks.

## Current behavior

- Scout: gets latest token profiles from DEX Screener and fetches available Solana token pairs.
- Filter: checks observable market requirements and blocks candidates when required security evidence is missing.
- Analyst: computes a transparent heuristic score (not a predictive AI model).
- Executor: paper-only simulated entries/exits, with configurable paper balance, position cap, stop-loss and trailing stop.
- Risk: rejects over-sized trades and applies simulated stop logic.
- Logger: records candidates, decisions and paper trades to local SQLite.

## Not yet implemented

This is deliberately not a turnkey live trading bot. Before live trading, a developer would need to implement and independently test on-chain token authority checks, LP ownership/lock verification across pool types, holder concentration, developer-wallet clustering/history, executable swap routing, transaction simulation, secure signing, RPC failover, monitoring, and an emergency kill switch. Live execution must remain disabled until those pieces are complete and audited.

## Data source

The live mode uses DEX Screener's documented public endpoints:
- `https://api.dexscreener.com/token-profiles/latest/v1`
- `https://api.dexscreener.com/tokens/v1/solana/{tokenAddresses}`

Review their current documentation and rate limits: https://docs.dexscreener.com/api/reference

The data source can be delayed, incomplete, rate-limited, or unavailable. Do not treat it as a guarantee of tradability.
