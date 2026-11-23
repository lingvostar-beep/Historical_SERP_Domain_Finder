import json
from pathlib import Path

for name in [
    "diag_legacy_amazon_us_nodate.json",
    "diag_current_amazon_au_sep.json",
    "diag_current_facebook_us_nodate.json",
]:
    b = json.loads(Path("spike/results", name).read_text(encoding="utf-8"))
    res = b["tasks"][0]["result"][0]
    print("====", name, "cost", b.get("cost"), "items_count", res.get("items_count"))
    for i, snap in enumerate(res.get("items") or []):
        org = sum(
            1
            for x in (snap.get("items") or [])
            if isinstance(x, dict) and x.get("type") == "organic"
        )
        print(
            f"  snap{i} datetime={snap.get('datetime')} organic={org} "
            f"items_count={snap.get('items_count')}"
        )
