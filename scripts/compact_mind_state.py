#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.state_compaction import compact_json_value, estimate_json_size, maybe_compact_json_state


ROOT = Path("/home/funboy/latent-somatic")
MIND = ROOT / "data" / "mind"
ARCHIVE = ROOT / "data" / "archive" / "manual-pre-resource-governor"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _dedupe_learning_lists(payload: Any) -> Any:
    if isinstance(payload, list):
        seen: set[str] = set()
        deduped: list[Any] = []
        for item in payload:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(_dedupe_learning_lists(item))
        return deduped
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            low = str(key).lower()
            if isinstance(value, list) and any(token in low for token in ("fact", "lesson", "learning", "memory")):
                cleaned[key] = _dedupe_learning_lists(value)
            else:
                cleaned[key] = _dedupe_learning_lists(value)
        return cleaned
    return payload


def compact_self_model(path: Path, *, apply: bool) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        payload = {"payload": payload}
    compacted = compact_json_value(_dedupe_learning_lists(payload))
    before = path.stat().st_size if path.exists() else 0
    after = estimate_json_size(compacted)
    archived_to = ""
    applied = False
    if apply and path.exists() and after < before:
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        archived = ARCHIVE / f"{path.name}.{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.bak"
        shutil.copy2(path, archived)
        _save_json(path, compacted)
        archived_to = str(archived)
        applied = True
    return {
        "path": str(path),
        "applied": applied,
        "archived_to": archived_to,
        "original_bytes": before,
        "compacted_bytes": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact oversized Soma mind state with archived originals.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Inspect and report without changing files.")
    mode.add_argument("--apply", action="store_true", help="Archive originals and write compacted state.")
    args = parser.parse_args()

    apply = bool(args.apply)
    targets = [
        MIND / "bios_state.json",
        MIND / "internal_loop_state.json",
        MIND / "self_model.json",
    ]

    reports: list[dict[str, Any]] = []
    for path in targets:
        if path.name == "self_model.json":
            reports.append(compact_self_model(path, apply=apply))
        else:
            reports.append(maybe_compact_json_state(path, apply=apply, archive_dir=ARCHIVE))

    print(json.dumps({"apply": apply, "reports": reports}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
