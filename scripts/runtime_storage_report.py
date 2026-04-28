#!/usr/bin/env python3
"""
scripts/runtime_storage_report.py — Report current runtime log sizes and health.

Usage:
    python3 scripts/runtime_storage_report.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f}KB"
    if n < 1024 ** 3:
        return f"{n/1024**2:.1f}MB"
    return f"{n/1024**3:.2f}GB"


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _first_last_ts(path: Path) -> tuple[float | None, float | None]:
    first: float | None = None
    last: float | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ts = float(obj.get("timestamp", 0))
                    if ts > 0:
                        if first is None:
                            first = ts
                        last = ts
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
    except OSError:
        pass
    return first, last


def _ts_str(ts: float | None) -> str:
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _estimate_dupe_ratio(path: Path, sample: int = 2000) -> float:
    """Estimate duplication by sampling lines and counting unique first-field combos."""
    seen: set[str] = set()
    total = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                if total > sample:
                    break
                try:
                    obj = json.loads(line)
                    key = json.dumps({
                        k: obj[k] for k in ("phase", "scenario", "provider")
                        if k in obj
                    }, sort_keys=True)
                    seen.add(key)
                except Exception:
                    pass
    except OSError:
        pass
    if total == 0:
        return 0.0
    return round(1.0 - len(seen) / total, 3)


def report_file(label: str, path: Path) -> dict:
    size = path.stat().st_size if path.exists() else 0
    lines = _count_lines(path) if path.exists() else 0
    first_ts, last_ts = _first_last_ts(path) if path.exists() else (None, None)
    dupe = _estimate_dupe_ratio(path) if path.exists() and size > 0 else 0.0
    age_s = None
    if last_ts:
        import time
        age_s = round(time.time() - last_ts, 0)

    print(f"\n  {label}")
    print(f"    path:       {path}")
    print(f"    size:       {_fmt_size(size)}")
    print(f"    lines:      {lines:,}")
    print(f"    oldest:     {_ts_str(first_ts)}")
    print(f"    newest:     {_ts_str(last_ts)}")
    if age_s is not None:
        print(f"    last write: {age_s:.0f}s ago")
    print(f"    est. dupe:  {dupe:.0%}")

    rec = ""
    if size > 50 * 1024 * 1024:
        rec = "WARNING: file exceeds 50MB — run compact_runtime_logs.py"
    elif size > 10 * 1024 * 1024:
        rec = "NOTICE: file exceeds 10MB — consider compaction"
    elif size == 0:
        rec = "empty"
    if rec:
        print(f"    status:     {rec}")

    return {"label": label, "path": str(path), "size_bytes": size, "lines": lines,
            "dupe_ratio": dupe, "recommendation": rec}


def scan_dir(label: str, path: Path) -> None:
    if not path.exists():
        print(f"\n  {label}: (not found)")
        return
    total = 0
    count = 0
    for f in sorted(path.rglob("*")):
        if f.is_file():
            s = f.stat().st_size
            total += s
            count += 1
    print(f"\n  {label}: {count} files, {_fmt_size(total)} total")


def main() -> None:
    print("=" * 60)
    print("  Soma Runtime Storage Report")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    print("\n[Legacy runtime logs]")
    report_file("cognitive_trace.jsonl", _REPO_ROOT / "data" / "mind" / "cognitive_trace.jsonl")
    report_file("actuation_history.jsonl", _REPO_ROOT / "data" / "runtime" / "actuation_history.jsonl")

    print("\n[Journal hot files]")
    hot_dir = _REPO_ROOT / "data" / "journal" / "hot"
    if hot_dir.exists():
        for f in sorted(hot_dir.glob("*.jsonl")):
            report_file(f.name, f)
    else:
        print("  (journal not initialized yet)")

    print("\n[Directory summaries]")
    scan_dir("data/journal/archive", _REPO_ROOT / "data" / "journal" / "archive")
    scan_dir("data/journal/daily", _REPO_ROOT / "data" / "journal" / "daily")
    scan_dir("data/autobiography", _REPO_ROOT / "data" / "autobiography")
    scan_dir("data/mind", _REPO_ROOT / "data" / "mind")
    scan_dir("data/memory", _REPO_ROOT / "data" / "memory")

    print("\n[Disk free]")
    import shutil
    usage = shutil.disk_usage(_REPO_ROOT)
    print(f"  free: {_fmt_size(usage.free)}  used: {_fmt_size(usage.used)}  total: {_fmt_size(usage.total)}")

    print()


if __name__ == "__main__":
    main()
