import requests
from datetime import datetime, timezone

BASE = "https://api.dexscreener.com"
TIMEOUT = 12

def fetch_live_candidates(limit=30):
    """Fetch latest token profiles, then available Solana pairs for up to 30 addresses."""
    resp = requests.get(f"{BASE}/token-profiles/latest/v1", timeout=TIMEOUT)
    resp.raise_for_status()
    profiles = resp.json()
    addresses = []
    for item in profiles if isinstance(profiles, list) else []:
        if item.get("chainId") == "solana" and item.get("tokenAddress"):
            addr = item["tokenAddress"]
            if addr not in addresses:
                addresses.append(addr)
        if len(addresses) >= limit:
            break
    if not addresses:
        return []
    pairs_resp = requests.get(f"{BASE}/tokens/v1/solana/{','.join(addresses)}", timeout=TIMEOUT)
    pairs_resp.raise_for_status()
    pairs = pairs_resp.json()
    candidates = []
    seen = set()
    for p in pairs if isinstance(pairs, list) else []:
        if p.get("chainId") != "solana":
            continue
        base = p.get("baseToken") or {}
        address = base.get("address")
        if not address or address in seen:
            continue
        seen.add(address)
        liquidity = (p.get("liquidity") or {}).get("usd")
        volume = (p.get("volume") or {}).get("h1")
        candidates.append({
            "symbol": base.get("symbol", "?"),
            "name": base.get("name", "Unknown"),
            "address": address,
            "pair_address": p.get("pairAddress"),
            "dex_id": p.get("dexId"),
            "price_usd": _float(p.get("priceUsd")),
            "liquidity_usd": _float(liquidity),
            "volume_h1_usd": _float(volume),
            "price_change_h1_pct": _float((p.get("priceChange") or {}).get("h1")),
            "txns_h1": _txn_count(p.get("txns")),
            "url": p.get("url"),
            "pair_created_at": p.get("pairCreatedAt"),
            "mint_authority_revoked": None,
            "lp_locked_or_burned": None,
            "top10_holder_pct": None,
            "dev_wallet_rug_history": None,
            "source": "dexscreener",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
    return candidates

def _float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None

def _txn_count(txns):
    if not isinstance(txns, dict):
        return None
    h1 = txns.get("h1") or {}
    try:
        return int(h1.get("buys", 0)) + int(h1.get("sells", 0))
    except (TypeError, ValueError):
        return None

def demo_candidates():
    """Synthetic candidates for testing workflow only; never real market data."""
    return [
        {"symbol":"DEMO1","name":"Demo Momentum","address":"DEMO_MINT_001","price_usd":0.010,
         "liquidity_usd":85000,"volume_h1_usd":94000,"price_change_h1_pct":8.2,"txns_h1":260,
         "mint_authority_revoked":True,"lp_locked_or_burned":True,"top10_holder_pct":14.0,
         "dev_wallet_rug_history":False,"source":"synthetic_demo"},
        {"symbol":"DEMO2","name":"Demo Risky Holder Mix","address":"DEMO_MINT_002","price_usd":0.004,
         "liquidity_usd":72000,"volume_h1_usd":88000,"price_change_h1_pct":4.5,"txns_h1":180,
         "mint_authority_revoked":True,"lp_locked_or_burned":True,"top10_holder_pct":28.0,
         "dev_wallet_rug_history":False,"source":"synthetic_demo"},
        {"symbol":"DEMO3","name":"Demo Missing Proofs","address":"DEMO_MINT_003","price_usd":0.020,
         "liquidity_usd":50000,"volume_h1_usd":67000,"price_change_h1_pct":11.0,"txns_h1":140,
         "mint_authority_revoked":None,"lp_locked_or_burned":None,"top10_holder_pct":None,
         "dev_wallet_rug_history":None,"source":"synthetic_demo"},
        {"symbol":"DEMO4","name":"Demo Thin Volume","address":"DEMO_MINT_004","price_usd":0.002,
         "liquidity_usd":45000,"volume_h1_usd":12000,"price_change_h1_pct":2.0,"txns_h1":40,
         "mint_authority_revoked":True,"lp_locked_or_burned":True,"top10_holder_pct":12.0,
         "dev_wallet_rug_history":False,"source":"synthetic_demo"},
    ]
