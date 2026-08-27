"""Record the current OpenRouter metadata for locked models."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cfg_path = ROOT / "config" / "models.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    wanted = {m["openrouter_slug"] for m in cfg["models"].values()}
    data = requests.get("https://openrouter.ai/api/v1/models", timeout=60).json()["data"]
    selected = [row for row in data if row["id"] in wanted]
    if len(selected) != len(wanted):
        found = {row["id"] for row in selected}
        missing = sorted(wanted - found)
        raise SystemExit(f"missing model metadata: {missing}")
    snapshot = {
        "snapshot_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "https://openrouter.ai/api/v1/models",
        "models": selected,
    }
    out = ROOT / "config" / "model_price_snapshot.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    cfg["api_snapshot_date"] = snapshot["snapshot_utc"][:10]
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

