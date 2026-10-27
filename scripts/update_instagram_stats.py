#!/usr/bin/env python3
"""Publish only public Instagram account totals. Keep Windsor credentials secret."""
import json
import os
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

key = os.environ.get("WINDSOR_API_KEY")
if not key:
    raise SystemExit("Missing WINDSOR_API_KEY GitHub Actions secret")
query = urllib.parse.urlencode({
    "api_key": key,
    "fields": "followers_count,media_count",
    "select_accounts": "17841401628895978",
    "date_preset": "last_7dT",
    "_renderer": "json",
})
request = urllib.request.Request(
    "https://connectors.windsor.ai/instagram?" + query,
    headers={"User-Agent": "Windsor/1.0", "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
except Exception as exc:
    # Avoid printing a URL that contains the secret key.
    raise SystemExit("Instagram fetch failed. Check Windsor connection and API key.") from None
rows = payload.get("data") if isinstance(payload, dict) else None
if not isinstance(rows, list) or not rows:
    raise SystemExit("Instagram API returned no rows; preserving last good snapshot")
row = rows[0]
try:
    followers = int(row["followers_count"])
    posts = int(row["media_count"]) if row.get("media_count") is not None else None
    if followers < 0 or (posts is not None and posts < 0):
        raise ValueError("Negative metric")
except (KeyError, TypeError, ValueError):
    raise SystemExit("Instagram API returned invalid metrics; preserving last good snapshot")
out = {
    "platform": "instagram",
    "followers": followers,
    "posts": posts,
    "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
path = pathlib.Path("data/instagram-stats.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
