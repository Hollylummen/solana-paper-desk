import streamlit as st
import pandas as pd
from solana_desk.engine import DeskEngine
from solana_desk.market_data import fetch_live_candidates, demo_candidates

st.set_page_config(page_title="Solana Paper Desk", page_icon="📊", layout="wide")
st.title("📊 Solana Memecoin Paper Desk — Phase 2")
st.caption("Paper trading only • No wallet connection • No live transactions")
st.warning("Live market discovery is WATCHLIST-ONLY. On-chain security verification is not implemented. Streamlit Cloud may sleep or restart, so this app is NOT an unattended overnight trading engine.")

with st.sidebar:
    st.header("Desk controls")
    source = st.radio("Data source", ["Demo data", "Live market discovery"])
    starting_balance = st.number_input("Paper starting balance (USD)", min_value=100.0, max_value=1_000_000.0, value=1000.0, step=100.0)
    position_pct = st.slider("Max position (% of equity)", 1, 8, 8)
    stop_pct = st.slider("Paper stop-loss (%)", 1, 20, 6)
    trail_start = st.slider("Start trailing after profit (%)", 1, 50, 12)
    min_score = st.slider("Minimum analyst score", 0.0, 1.0, 0.60, 0.05)
    min_liquidity = st.number_input("Minimum liquidity (USD)", min_value=0, value=20000, step=5000)
    min_volume = st.number_input("Minimum 1h volume (USD)", min_value=0, value=50000, step=10000)
    run_scan = st.button("🔎 Scan candidates", type="primary", use_container_width=True)
    st.divider()
    st.warning("This starter has no live trading capability. Demo data is synthetic.")

engine = DeskEngine(db_path="paper_desk.sqlite3", starting_balance=float(starting_balance),
                    position_pct=float(position_pct)/100, stop_pct=float(stop_pct)/100,
                    trail_start=float(trail_start)/100, min_score=float(min_score),
                    min_liquidity=float(min_liquidity), min_volume=float(min_volume))

if "candidates" not in st.session_state:
    st.session_state.candidates = []
if "last_scan_note" not in st.session_state:
    st.session_state.last_scan_note = "No scan run yet."

if run_scan:
    with st.spinner("Scanning token profiles and available Solana pairs..."):
        if source == "Demo data":
            st.session_state.candidates = demo_candidates()
            st.session_state.last_scan_note = "Synthetic demo data loaded. No real token prices or trades."
        else:
            try:
                st.session_state.candidates = fetch_live_candidates()
                st.session_state.last_scan_note = "Live market data fetched. Missing security proofs are treated as failed checks."
            except Exception as exc:
                st.session_state.last_scan_note = f"Scan failed: {type(exc).__name__}: {exc}"
                st.session_state.candidates = []

candidates = st.session_state.candidates
st.info(st.session_state.last_scan_note)

summary = engine.summary()
a,b,c,d = st.columns(4)
a.metric("Paper equity", f"${summary['equity']:,.2f}", f"{summary['equity']-starting_balance:+,.2f} vs starting")
b.metric("Open positions", str(summary["open_positions"]))
c.metric("Closed paper trades", str(summary["closed_trades"]))
d.metric("Win rate", f"{summary['win_rate']:.1f}%")

if candidates:
    st.subheader("Scout → Filter → Analyst")
    results = engine.process_candidates(candidates, allow_demo=(source == "Demo data"))
    df = pd.DataFrame(results)
    if not df.empty:
        display_cols = [c for c in ["symbol","name","price_usd","liquidity_usd","volume_h1_usd","score","filter_status","decision","reason"] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
else:
    st.subheader("Candidate feed")
    st.write("Click **Scan candidates** to load demo or live market data.")

st.subheader("Open paper positions")
positions = engine.open_positions()
if positions:
    st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)
else:
    st.write("No open paper positions.")

st.subheader("Recent audit log")
events = engine.recent_events(limit=50)
if events:
    st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
else:
    st.write("No events recorded yet.")

st.subheader("Risk and implementation status")
st.markdown("""
- **Position cap:** at most the configured percentage of current paper equity.
- **Stop-loss:** simulated from observed prices; gaps and missing quotes are not protected.
- **Trailing stop:** activates only after the configured profit threshold.
- **Security gate:** live candidates are rejected until mint authority, LP status, top-holder concentration, and developer-wallet history are independently verified.
- **Live execution:** intentionally absent. Do not add a wallet key to this project.
""")


st.subheader("🧪 Test simulated exits (demo positions only)")
st.caption("This manually changes a synthetic demo token's mark price to exercise the simulated stop and trailing-stop logic. It does not fetch live prices.")
demo_positions = [p for p in engine.open_positions() if p.get("source") == "synthetic_demo"]
if demo_positions:
    symbols = [p["symbol"] for p in demo_positions]
    chosen = st.selectbox("Demo position", symbols)
    pos = next(p for p in demo_positions if p["symbol"] == chosen)
    change = st.slider("Simulated price move from entry (%)", -95, 200, 0, 1)
    proposed_price = float(pos["entry_price"]) * (1 + change/100)
    if st.button("Apply synthetic price update"):
        engine.mark_prices({chosen: proposed_price})
        st.success("Synthetic price updated. Refreshing view...")
        st.rerun()
else:
    st.write("Run Demo data → Scan candidates to open a synthetic test position.")

st.subheader("📄 Download your paper-trading records")
import io
from datetime import datetime, timezone
all_events = engine.all_events()
if all_events:
    st.download_button("Download decision and activity log (CSV)",
        data=pd.DataFrame(all_events).to_csv(index=False).encode("utf-8"),
        file_name="solana_paper_desk_audit.csv", mime="text/csv")
closed = engine.closed_positions()
if closed:
    st.dataframe(pd.DataFrame(closed), use_container_width=True, hide_index=True)
    st.download_button("Download closed paper trades (CSV)",
        data=pd.DataFrame(closed).to_csv(index=False).encode("utf-8"),
        file_name="solana_paper_desk_closed_trades.csv", mime="text/csv")
st.caption("Important: SQLite records on free Streamlit hosting can disappear after app restarts or redeployments. Download CSVs regularly. This is not durable storage.")
