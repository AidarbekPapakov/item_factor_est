"""
Probe CSFloat's undocumented sales-history endpoint and inspect the response shape.

  GET https://csfloat.com/api/v1/history/{url_escaped_market_hash_name}/sales?paint_index={int}
  Header: Authorization: <API_KEY>

Goal of this script: confirm the endpoint works, see how deep the history goes per item,
and verify which fields (fade, blue_gem, reference.predicted_price, stickers[].reference.price)
are actually populated in the wild before committing to a schema.

Usage:
  export CSFLOAT_API_KEY=...
  python scripts/test_csfloat_history.py "AK-47 | Vulcan (Minimal Wear)"
  python scripts/test_csfloat_history.py "AK-47 | Case Hardened (Minimal Wear)" --paint-index 44 --save resp.json
"""
import argparse
import json
import os
import statistics
import sys
from typing import Any
from urllib.parse import quote

import httpx

BASE_URL = "https://csfloat.com/api/v1"


def fetch_sales_history(
    market_hash_name: str, paint_index: int | None, api_key: str
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    
    url = f"{BASE_URL}/history/{quote(market_hash_name)}/sales"
    params: dict[str, int] = {}
    if paint_index:  # 0 returns empty per the reverse-engineered docs
        params["paint_index"] = paint_index

    with httpx.Client(timeout=20) as client:
        r = client.get(url, headers={"Authorization": api_key}, params=params)

    rate_headers = {
        k: v for k, v in r.headers.items() if k.lower().startswith("x-ratelimit")
    }
    print(f"HTTP {r.status_code}  |  rate-limit headers: {rate_headers or '(none returned)'}")

    if r.status_code != 200:
        print(f"Error body: {r.text[:500]}")
        r.raise_for_status()

    data = r.json()
    if not isinstance(data, list):
        # Empty/disabled history sometimes returns an error object instead of []
        print(f"Non-list response (likely SalesHistoryNotAvailable): {data}")
        return [], rate_headers
    return data, rate_headers


def summarize(data: list[dict[str, Any]]) -> None:
    if not data:
        print("\nNo sales returned — either no recorded sales or history disabled for this item.")
        return

    print(f"\n--- {len(data)} sales returned ---")

    prices_usd = sorted(entry["price"] / 100 for entry in data)
    print(
        f"Price (USD): min ${prices_usd[0]:.2f}  "
        f"median ${statistics.median(prices_usd):.2f}  "
        f"max ${prices_usd[-1]:.2f}  "
        f"max/median ratio {prices_usd[-1] / statistics.median(prices_usd):.2f}x"
    )
    timestamps = sorted(entry["sold_at"] for entry in data)
    print(f"Time range: {timestamps[0]} → {timestamps[-1]}")

    first = data[0]
    item = first.get("item", {})
    ref = first.get("reference", {})

    print(f"\n--- First entry ---")
    print(f"  sold_at:   {first.get('sold_at')}")
    print(f"  price:     ${first['price'] / 100:.2f}")
    print(f"  float:     {item.get('float_value')}")
    print(f"  seed:      {item.get('paint_seed')}")
    print(f"  stickers:  {len(item.get('stickers') or [])}")
    print(f"  charms:    {len(item.get('keychains') or [])}")

    if item.get("fade"):
        print(f"  fade:      {item['fade']}")
    if item.get("blue_gem"):
        print(f"  blue_gem:  {item['blue_gem']}")

    if ref:
        base = ref.get("base_price", 0) / 100
        pred = ref.get("predicted_price", 0) / 100
        sold = first["price"] / 100
        print(
            f"\n  CSFloat reference:"
            f"\n    base_price        = ${base:.2f}"
            f"\n    float_factor      = {ref.get('float_factor')}"
            f"\n    keychain_price    = ${ref.get('keychain_price', 0) / 100:.2f}"
            f"\n    predicted_price   = ${pred:.2f}"
            f"\n    actual sold       = ${sold:.2f}"
            f"\n    sold / predicted  = {sold / pred:.3f}x   <-- Model C target candidate"
        )

    # Quick distribution sanity-check across all sales for the target framing decision
    refs_with_pred = [e for e in data if e.get("reference", {}).get("predicted_price")]
    if len(refs_with_pred) >= 3:
        ratios = sorted(
            e["price"] / e["reference"]["predicted_price"] for e in refs_with_pred
        )
        med = statistics.median(ratios)
        print(
            f"\n--- sold/predicted ratio across {len(ratios)} entries ---"
            f"\n  min {ratios[0]:.3f}  median {med:.3f}  max {ratios[-1]:.3f}  "
            f"max/median {ratios[-1] / med:.2f}x"
        )
        print("  (heuristic: max/median > 5 suggests log target for Model C)")


def main() -> None:
    api_key: str = 'api_key'
    
    market_hash_name: str = "AK-47 | Vulcan (Minimal Wear)"
    # paint_index: int = 44
    save_json: bool = True
    json_filename = f"{market_hash_name.replace(' ', '_').lower()}_sales_history.json"

    data, _ = fetch_sales_history(
        market_hash_name=market_hash_name, 
        paint_index=None,
        api_key=api_key)
    
    summarize(data)

    if save_json:
        with open(json_filename, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"\nFull response saved to {json_filename}")


if __name__ == "__main__":
    main()
