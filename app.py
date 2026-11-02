import os
import streamlit as st
import pandas as pd
import psycopg2
from solana_desk.engine import DeskEngine
from solana_desk.market_data import fetch_live_candidates, demo_candidates

st.set_page_config(page_title="Solana Paper Desk", page_icon="📊", layout="wide")
st.title("📊 Solana Memecoin Paper Desk")
st.caption("Paper trading only • No wallet connection • No live transactions")


def read_bot_state():
    """Read-only access to the Render worker's saved JSONB state."""
    url = st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    if not url:
        return None, None, "Database connection not configured in Streamlit secrets."
    try:
        with psycopg2.connect(url, connect_timeout=10, options="-c statement_timeout=10000") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state, updated_at FROM paper_bot_state WHERE bot_id = %s", ("main",))
                record = cur.fetchone()
        if record is None:
            return None, None, "No saved bot account found."
        return record[0], record[1], None
    except psycopg2.Error:
        return None, None, "Unable to read PostgreSQL. Check the Streamlit secret, database access, and database status."


def closed_trade_frame(closed):
    """Normalize completed trades; missing P&L is not assumed to be zero."""
    if not closed:
        return pd.DataFrame()
    df = pd.DataFrame(closed)
    if "pnl_usd" not in df.columns:
        df["pnl_usd"] = float("nan")
    df["pnl_usd"] = pd.to_numeric(df["pnl_usd"], errors="coerce")
    if "symbol" not in df.columns:
        df["symbol"] = "Unknown"
    df["symbol"] = df["symbol"].fillna("Unknown").astype(str)
    if "at" in df.columns:
        df["closed_at"] = pd.to_datetime(df["at"], errors="coerce", utc=True)
    else:
        df["closed_at"] = pd.NaT
    return df


bot_tab, demo_tab = st.tabs(["🤖 Bot results (Render)", "🧪 Separate demo desk"])

with bot_tab:
    st.caption("Read-only snapshot of the Render bot. Refresh this page for newer values; no trades are placed here.")
    state, updated, problem = read_bot_state()
    if problem:
        st.warning(problem)
    else:
        cash = float(state.get("cash", 0))
        positions = state.get("positions", {}) or {}
        closed = state.get("closed", []) or []
        trades = state.get("trades", []) or []
        equity = float(state.get("last_equity", cash))
        closed_df = closed_trade_frame(closed)
        valid = closed_df.dropna(subset=["pnl_usd"]) if not closed_df.empty else pd.DataFrame()
        wins = int((valid["pnl_usd"] > 0).sum()) if not valid.empty else 0
        a, b, c, d = st.columns(4)
        a.metric("Last recorded paper equity", f"${equity:,.2f}")
        b.metric("Paper cash", f"${cash:,.2f}")
        c.metric("Open positions", len(positions))
        d.metric("Closed trades", len(closed))
        if not valid.empty:
            st.caption(f"Saved to database: {updated} · Closed-trade win rate: {wins / len(valid) * 100:.1f}% (of {len(valid)} trades with recorded P&L)")
        else:
            st.caption(f"Saved to database: {updated} · No completed trades with recorded P&L yet")
        st.info("Equity is the bot's last recorded estimate, not a live quote. Prices, fills, and returns are simulated.")

        st.subheader("📈 Performance overview")
        if valid.empty:
            st.write("Performance statistics will appear when completed trades with P&L are recorded.")
        else:
            net_pnl = float(valid["pnl_usd"].sum())
            losses = int((valid["pnl_usd"] < 0).sum())
            breakeven = int((valid["pnl_usd"] == 0).sum())
            avg_pnl = float(valid["pnl_usd"].mean())
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Realized simulated P&L", f"${net_pnl:+,.2f}")
            p2.metric("Win rate", f"{wins / len(valid) * 100:.1f}%")
            p3.metric("Winning / losing", f"{wins} / {losses}")
            p4.metric("Average P&L per close", f"${avg_pnl:+,.2f}")
            st.caption(f"Based on {len(valid)} completed trades with numeric P&L; {breakeven} break-even. Excludes open-position gains/losses, fees not recorded by the bot, and any missing P&L values.")

            # Preserve the stored order when timestamps are absent or duplicated.
            ordered = valid.copy()
            ordered["record_order"] = range(len(ordered))
            ordered = ordered.sort_values(["closed_at", "record_order"], na_position="last", kind="stable")
            ordered["Cumulative realized P&L (USD)"] = ordered["pnl_usd"].cumsum()
            ordered["Completed trade"] = range(1, len(ordered) + 1)
            st.subheader("Cumulative realized simulated P&L")
            st.line_chart(ordered.set_index("Completed trade")[["Cumulative realized P&L (USD)"]])

            st.subheader("Performance by token")
            by_token = (valid.groupby("symbol", dropna=False)
                        .agg(trades=("pnl_usd", "size"), net_pnl_usd=("pnl_usd", "sum"),
                             wins=("pnl_usd", lambda x: int((x > 0).sum())))
                        .reset_index())
            by_token["win_rate_pct"] = (100 * by_token["wins"] / by_token["trades"]).round(1)
            by_token = by_token.sort_values("net_pnl_usd", ascending=False)
            st.dataframe(by_token.rename(columns={"symbol": "Token", "trades": "Closed trades",
                                                       "net_pnl_usd": "Net P&L (USD)", "wins": "Wins",
                                                       "win_rate_pct": "Win rate (%)"}),
                         use_container_width=True, hide_index=True)
            best = valid.loc[valid["pnl_usd"].idxmax()]
            worst = valid.loc[valid["pnl_usd"].idxmin()]
            t1, t2 = st.columns(2)
            t1.metric("Best completed trade", f"{best['symbol']}: ${best['pnl_usd']:+,.2f}")
            t2.metric("Worst completed trade", f"{worst['symbol']}: ${worst['pnl_usd']:+,.2f}")

        st.subheader("Open simulated positions")
        if positions:
            rows = [{"address": addr, **pos} for addr, pos in positions.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.write("No open positions.")
        st.subheader("Recent simulated trades")
        if trades:
            st.dataframe(pd.DataFrame(trades[-50:][::-1]), use_container_width=True, hide_index=True)
        else:
            st.write("No trades recorded yet.")
        st.subheader("Closed simulated trades")
        if closed:
            st.dataframe(pd.DataFrame(closed[-50:][::-1]), use_container_width=True, hide_index=True)
        else:
            st.write("No closed trades yet.")

with demo_tab:
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
