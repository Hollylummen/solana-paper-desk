"""Six small, explicit agent roles. Each returns structured output for the next stage."""

def scout(candidate):
    return {"candidate": candidate, "handoff": "scout_to_filter"}

def filter_agent(candidate, min_liquidity, min_volume):
    failures = []
    if candidate.get("mint_authority_revoked") is not True:
        failures.append("mint authority not verified revoked")
    if candidate.get("lp_locked_or_burned") is not True:
        failures.append("LP lock/burn not verified")
    top10 = candidate.get("top10_holder_pct")
    if top10 is None:
        failures.append("top-10 holder concentration unknown")
    elif float(top10) > 20:
        failures.append(f"top-10 holders exceed 20% ({top10:.1f}%)")
    if candidate.get("dev_wallet_rug_history") is not False:
        failures.append("developer-wallet rug history not cleared")
    liq = candidate.get("liquidity_usd")
    if liq is None or float(liq) < min_liquidity:
        failures.append(f"liquidity below minimum or unavailable (${min_liquidity:,.0f})")
    vol = candidate.get("volume_h1_usd")
    if vol is None or float(vol) < min_volume:
        failures.append(f"1h volume below minimum or unavailable (${min_volume:,.0f})")
    return {"passed": not failures, "failures": failures, "handoff": "filter_to_analyst" if not failures else "filter_to_logger"}

def analyst(candidate):
    """Transparent heuristic score, not ML and not a return prediction."""
    score = 0.0
    liq = candidate.get("liquidity_usd") or 0
    vol = candidate.get("volume_h1_usd") or 0
    txns = candidate.get("txns_h1") or 0
    change = candidate.get("price_change_h1_pct")
    # Score components reward basic market depth and activity, while avoiding extreme short-term spikes.
    score += min(liq / 100000, 1.0) * 0.35
    score += min(vol / 150000, 1.0) * 0.35
    score += min(txns / 300, 1.0) * 0.20
    if change is not None and -10 <= float(change) <= 25:
        score += 0.10
    return round(min(score, 1.0), 3)

def executor(candidate, score, risk):
    """Paper-only entry request; this module has no transaction signing capability."""
    if score < risk["min_score"]:
        return {"approved": False, "reason": f"score {score:.3f} below threshold {risk['min_score']:.2f}"}
    if not candidate.get("price_usd") or candidate["price_usd"] <= 0:
        return {"approved": False, "reason": "missing or invalid price"}
    return {"approved": True, "reason": "paper entry eligible"}

def risk_agent(equity, position_pct, open_exposure):
    max_position = max(0.0, equity * position_pct)
    available = max(0.0, equity - open_exposure)
    return {"max_position_usd": min(max_position, available), "handoff": "risk_to_executor"}

def logger_agent(event_type, message):
    return {"event_type": event_type, "message": message}
