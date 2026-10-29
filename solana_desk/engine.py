import sqlite3, json, time
from datetime import datetime, timezone
from .agents import scout, filter_agent, analyst, executor, risk_agent, logger_agent

def now():
    return datetime.now(timezone.utc).isoformat()

class DeskEngine:
    def __init__(self, db_path, starting_balance=1000.0, position_pct=.08, stop_pct=.06,
                 trail_start=.12, min_score=.60, min_liquidity=20000, min_volume=50000):
        self.db_path = db_path
        self.position_pct = position_pct
        self.stop_pct = stop_pct
        self.trail_start = trail_start
        self.min_score = min_score
        self.min_liquidity = min_liquidity
        self.min_volume = min_volume
        self._init_db(starting_balance)

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self, balance):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), starting_balance REAL, cash REAL)""")
            c.execute("""INSERT OR IGNORE INTO state(id,starting_balance,cash) VALUES(1,?,?)""", (balance,balance))
            c.execute("""CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT, symbol TEXT, qty REAL,
                entry_price REAL, current_price REAL, invested REAL, opened_at TEXT, status TEXT,
                exit_price REAL, pnl REAL, peak_price REAL, source TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event_type TEXT, symbol TEXT,
                message TEXT, data TEXT)""")

    def _log(self, event_type, symbol, message, data=None):
        with self._conn() as c:
            c.execute("INSERT INTO events(ts,event_type,symbol,message,data) VALUES(?,?,?,?,?)",
                      (now(), event_type, symbol, message, json.dumps(data or {})))

    def summary(self):
        with self._conn() as c:
            state = c.execute("SELECT starting_balance,cash FROM state WHERE id=1").fetchone()
            positions = c.execute("SELECT invested,current_price,qty,status,pnl FROM positions").fetchall()
        start, cash = state
        open_pos = [p for p in positions if p[3] == "OPEN"]
        closed = [p for p in positions if p[3] == "CLOSED"]
        equity = cash + sum((p[2] or 0) * (p[1] or 0) for p in open_pos)
        wins = sum(1 for p in closed if (p[4] or 0) > 0)
        win_rate = 100 * wins / len(closed) if closed else 0
        return {"starting_balance":start,"cash":cash,"equity":equity,"open_positions":len(open_pos),
                "closed_trades":len(closed),"win_rate":win_rate}

    def process_candidates(self, candidates, allow_demo=False):
        output = []
        for raw in candidates:
            candidate = scout(raw)["candidate"]
            symbol = candidate.get("symbol","?")
            checks = filter_agent(candidate, self.min_liquidity, self.min_volume)
            score = analyst(candidate)
            reason = "; ".join(checks["failures"]) if not checks["passed"] else "all configured filters passed"
            decision = "REJECT"
            if checks["passed"]:
                s = self.summary()
                open_positions = self.open_positions()
                exposure = sum(float(p["invested"]) for p in open_positions)
                risk = risk_agent(s["equity"], self.position_pct, exposure)
                request = executor(candidate, score, {"min_score":self.min_score})
                if request["approved"] and risk["max_position_usd"] >= 5:
                    # Demo positions only in synthetic mode; live candidates still need verified security data.
                    if allow_demo and candidate.get("source") == "synthetic_demo":
                        self._open_paper(candidate, risk["max_position_usd"])
                        decision = "PAPER BUY"
                        reason = "synthetic demo entry; not real market data"
                    else:
                        reason = "eligible market candidate, but live-security adapter is not implemented; no position opened"
                else:
                    reason = request.get("reason","risk manager denied position") if not request["approved"] else "insufficient available paper cash/exposure capacity"
            else:
                reason = "FILTER REJECT: " + reason
            self._log("candidate_decision", symbol, reason, {"score":score,"decision":decision,"address":candidate.get("address")})
            output.append({
                "symbol":symbol,"name":candidate.get("name"),"price_usd":candidate.get("price_usd"),
                "liquidity_usd":candidate.get("liquidity_usd"),"volume_h1_usd":candidate.get("volume_h1_usd"),
                "score":score,"filter_status":"PASS" if checks["passed"] else "FAIL",
                "decision":decision,"reason":reason,"address":candidate.get("address")
            })
        return output

    def _open_paper(self, candidate, amount):
        price = float(candidate["price_usd"])
        with self._conn() as c:
            state = c.execute("SELECT cash FROM state WHERE id=1").fetchone()
            cash = state[0]
            amount = min(amount, cash)
            if amount < 5:
                return
            qty = amount / price
            c.execute("UPDATE state SET cash=? WHERE id=1", (cash-amount,))
            c.execute("""INSERT INTO positions(address,symbol,qty,entry_price,current_price,invested,opened_at,status,peak_price,source)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (candidate["address"],candidate["symbol"],qty,price,price,amount,now(),"OPEN",price,candidate.get("source")))
        self._log("paper_entry", candidate["symbol"], f"Simulated entry ${amount:.2f} at ${price:g}", candidate)

    def open_positions(self):
        with self._conn() as c:
            rows = c.execute("""SELECT id,address,symbol,qty,entry_price,current_price,invested,opened_at,peak_price,source
                                FROM positions WHERE status='OPEN' ORDER BY opened_at DESC""").fetchall()
        result = []
        for r in rows:
            pid, address, symbol, qty, entry, current, invested, opened, peak, source = r
            pnl = qty * current - invested
            result.append({"id":pid,"symbol":symbol,"address":address,"qty":qty,"entry_price":entry,
                           "current_price":current,"invested":invested,"unrealized_pnl":pnl,
                           "opened_at":opened,"source":source})
        return result

    def mark_prices(self, price_map):
        """Update simulated marks; call with observed price updates. Closes positions on paper stop/trail."""
        with self._conn() as c:
            rows = c.execute("SELECT id,symbol,qty,entry_price,invested,current_price,peak_price FROM positions WHERE status='OPEN'").fetchall()
        for pid, symbol, qty, entry, invested, old_price, peak in rows:
            price = price_map.get(symbol)
            if not price or price <= 0:
                continue
            peak = max(peak or entry, price)
            stop = entry * (1-self.stop_pct)
            trail_active = peak >= entry*(1+self.trail_start)
            trail_stop = peak*(1-self.stop_pct) if trail_active else 0
            exit_reason = None
            if price <= stop:
                exit_reason = "paper hard stop reached"
            elif trail_active and price <= trail_stop:
                exit_reason = "paper trailing stop reached"
            with self._conn() as c:
                c.execute("UPDATE positions SET current_price=?,peak_price=? WHERE id=?", (price,peak,pid))
                if exit_reason:
                    proceeds = qty * price
                    pnl = proceeds - invested
                    c.execute("UPDATE positions SET status='CLOSED',exit_price=?,pnl=? WHERE id=?", (price,pnl,pid))
                    c.execute("UPDATE state SET cash=cash+? WHERE id=1", (proceeds,))
                    self._log("paper_exit", symbol, f"{exit_reason}; simulated P/L ${pnl:.2f}", {"price":price})
        self._log("mark_update", "*", f"Updated {len(price_map)} paper marks")

    def recent_events(self, limit=50):
        with self._conn() as c:
            rows = c.execute("SELECT ts,event_type,symbol,message FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"time":r[0],"event":r[1],"symbol":r[2],"message":r[3]} for r in rows]
