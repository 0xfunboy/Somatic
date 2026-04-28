#!/usr/bin/env python3
"""
scripts/compact_runtime_logs.py — Compact and archive large runtime JSONL logs.

Handles:
  - data/mind/cognitive_trace.jsonl
  - data/runtime/actuation_history.jsonl

Usage:
    python3 scripts/compact_runtime_logs.py --dry-run
    python3 scripts/compact_runtime_logs.py --apply
    python3 scripts/compact_runtime_logs.py --apply --delete-originals
    python3 scripts/compact_runtime_logs.py --apply --force   # ignore running server check
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_INPUT_FILES: list[tuple[str, Path]] = [
    ("cognitive_trace", _REPO_ROOT / "data" / "mind" / "cognitive_trace.jsonl"),
    ("actuation_history", _REPO_ROOT / "data" / "runtime" / "actuation_history.jsonl"),
]

_ARCHIVE_BASE = _REPO_ROOT / "data" / "journal" / "archive"
_DAILY_BASE = _REPO_ROOT / "data" / "journal" / "daily"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f}KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f}MB"
    return f"{n / 1024 ** 3:.2f}GB"


def _server_is_running() -> bool:
    """Return True if server.py appears to be running."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "server.py" in line and "grep" not in line:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Semantic hash implementations
# ---------------------------------------------------------------------------

def _actuation_semantic_hash(payload: dict[str, Any]) -> str:
    """Semantic hash for an actuation entry per spec."""
    sig = {
        "provider": payload.get("provider", {}).get("name", "")
        if isinstance(payload.get("provider"), dict)
        else str(payload.get("provider", "")),
        "scenario": payload.get("scenario", ""),
        "policy_mode": payload.get("policy", {}).get("mode", "")
        if isinstance(payload.get("policy"), dict)
        else str(payload.get("policy_mode", "")),
        "visible_actions": sorted(
            a.get("name", "")
            for a in (payload.get("actions") or [])
            if isinstance(a, dict) and a.get("visible")
        ),
    }
    canonical = json.dumps(sig, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


def _trace_semantic_hash(event: dict[str, Any]) -> str:
    """Semantic hash for a cognitive trace entry per spec."""
    sig = {
        "phase": event.get("phase", ""),
        "summary_prefix": event.get("summary", "")[:40],
        "level": event.get("level", ""),
    }
    canonical = json.dumps(sig, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


def _choose_hash_fn(name: str):
    """Select the right semantic hash function based on the log name."""
    if "actuation" in name:
        return _actuation_semantic_hash
    return _trace_semantic_hash


# ---------------------------------------------------------------------------
# Per-file processing (streaming, never loads all to memory)
# ---------------------------------------------------------------------------

class _FileStats:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.size_bytes: int = 0
        self.lines: int = 0
        self.unique_count: int = 0
        # hash -> {first_seen, last_seen, count, sample_line}
        self.dedup_map: dict[str, dict[str, Any]] = {}


def _process_file(stat: _FileStats, hash_fn) -> list[bytes]:
    """
    Stream-read the JSONL and deduplicate.
    Returns the list of unique raw lines (bytes) to write to the archive.
    Populates stat in place.
    """
    stat.size_bytes = stat.path.stat().st_size if stat.path.exists() else 0
    unique_lines: list[bytes] = []

    if not stat.path.exists() or stat.size_bytes == 0:
        return unique_lines

    with stat.path.open("rb") as f:
        for raw_bytes in f:
            stripped = raw_bytes.strip()
            if not stripped:
                continue
            stat.lines += 1
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                # Keep malformed lines verbatim (dedupe by raw sha1)
                h = hashlib.sha1(stripped).hexdigest()[:12]
                if h not in stat.dedup_map:
                    stat.dedup_map[h] = {
                        "first_seen": time.time(),
                        "last_seen": time.time(),
                        "count": 1,
                        "sample_line": stripped.decode("utf-8", errors="replace")[:200],
                    }
                    unique_lines.append(raw_bytes)
                else:
                    stat.dedup_map[h]["count"] += 1
                    stat.dedup_map[h]["last_seen"] = time.time()
                continue

            ts = float(payload.get("timestamp", 0.0))
            h = hash_fn(payload)

            if h not in stat.dedup_map:
                stat.dedup_map[h] = {
                    "first_seen": ts,
                    "last_seen": ts,
                    "count": 1,
                    "sample_line": stripped.decode("utf-8", errors="replace")[:300],
                }
                unique_lines.append(raw_bytes)
            else:
                stat.dedup_map[h]["count"] += 1
                stat.dedup_map[h]["last_seen"] = max(stat.dedup_map[h]["last_seen"], ts)

    stat.unique_count = len(stat.dedup_map)
    return unique_lines


# ---------------------------------------------------------------------------
# Autobiography markdown builder
# ---------------------------------------------------------------------------

def _build_autobiography(
    date_str: str,
    file_stats: list[_FileStats],
    total_input: int,
    total_unique: int,
) -> str:
    lines: list[str] = [f"# Soma Log Compaction — {date_str}", ""]

    # Summary section
    lines.append("## Summary")
    for stat in file_stats:
        if stat.lines == 0:
            continue
        pct = 100.0 * (1.0 - stat.unique_count / stat.lines) if stat.lines > 0 else 0.0
        lines.append(
            f"Compacted {stat.lines:,} {stat.path.name} events "
            f"→ {stat.unique_count:,} unique states "
            f"({pct:.1f}% reduction)."
        )
    lines.append("")

    # Per-file top patterns
    for stat in file_stats:
        if not stat.dedup_map:
            continue
        label = "Trace Patterns" if "trace" in stat.path.name else "Actuation Patterns"
        lines.append(f"## Top {label}")

        # Sort by count descending
        sorted_items = sorted(
            stat.dedup_map.items(),
            key=lambda kv: -kv[1]["count"],
        )
        for h, info in sorted_items[:10]:
            sample = info["sample_line"]
            try:
                obj = json.loads(sample)
                phase = obj.get("phase", obj.get("scenario", ""))
                summary = obj.get("summary", "")[:80]
                lines.append(f"- {phase} × {info['count']:,} — {summary}")
            except json.JSONDecodeError:
                lines.append(f"- [{h}] × {info['count']:,}")
        lines.append("")

    # Archived section
    lines.append("## Archived")
    for stat in file_stats:
        if stat.unique_count == 0:
            continue
        stem = stat.path.stem
        gz_name = f"{stem}.raw.jsonl.gz"
        lines.append(f"- {gz_name} (unique: {stat.unique_count:,} entries)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main compaction routine
# ---------------------------------------------------------------------------

def compact(
    *,
    dry_run: bool,
    delete_originals: bool,
    force: bool,
) -> dict[str, Any]:
    date_str = _today_str()
    errors: list[str] = []
    archive_paths: list[str] = []

    # ── Server check ──────────────────────────────────────────────────────────
    if not force and _server_is_running():
        msg = (
            "server.py appears to be running. Stop the server first, or use --force.\n"
            "Detected via: ps aux | grep server.py"
        )
        print(f"ABORT: {msg}", file=sys.stderr)
        return {
            "date": date_str,
            "input_files": [],
            "total_input_lines": 0,
            "unique_states": 0,
            "compressed_size_bytes": 0,
            "compression_ratio": 0.0,
            "saved_bytes": 0,
            "archive_paths": [],
            "errors": [msg],
            "dry_run": dry_run,
        }

    # ── Prepare archive directory ─────────────────────────────────────────────
    archive_day_dir = _ARCHIVE_BASE / date_str
    daily_dir = _DAILY_BASE

    if not dry_run:
        for d in (archive_day_dir, daily_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"mkdir {d}: {e}")

    # ── Process each input file ───────────────────────────────────────────────
    file_stats: list[_FileStats] = []
    input_file_reports: list[dict[str, Any]] = []
    total_input_lines = 0
    total_unique = 0
    total_original_bytes = 0
    total_compressed_bytes = 0

    for label, path in _INPUT_FILES:
        stat = _FileStats(path)
        hash_fn = _choose_hash_fn(label)

        if not path.exists():
            print(f"  [SKIP] {path.name} — not found")
            input_file_reports.append({
                "path": str(path),
                "size_bytes": 0,
                "lines": 0,
            })
            file_stats.append(stat)
            continue

        print(f"  [READ] {path.name} ({_fmt_size(path.stat().st_size)})")
        unique_lines = _process_file(stat, hash_fn)
        file_stats.append(stat)

        total_input_lines += stat.lines
        total_unique += stat.unique_count

        reduction = 100.0 * (1.0 - stat.unique_count / stat.lines) if stat.lines > 0 else 0.0
        print(
            f"         {stat.lines:,} lines → {stat.unique_count:,} unique "
            f"({reduction:.1f}% reduction)"
        )

        input_file_reports.append({
            "path": str(path),
            "size_bytes": stat.size_bytes,
            "lines": stat.lines,
        })

        # ── Write compressed archive ──────────────────────────────────────────
        gz_name = f"{path.stem}.raw.jsonl.gz"
        gz_path = archive_day_dir / gz_name
        original_bytes = sum(len(ln) for ln in unique_lines)
        total_original_bytes += original_bytes

        if dry_run:
            print(f"         [DRY-RUN] would write: {gz_path}")
            archive_paths.append(str(gz_path))
        else:
            try:
                with gzip.open(gz_path, "wb", compresslevel=6) as gz:
                    for line in unique_lines:
                        gz.write(line)
                compressed = gz_path.stat().st_size
                total_compressed_bytes += compressed
                archive_paths.append(str(gz_path))
                print(f"         archived → {gz_path.name} ({_fmt_size(compressed)})")
            except OSError as e:
                errors.append(f"compress {gz_path}: {e}")

    # ── Saved/ratio ───────────────────────────────────────────────────────────
    saved_bytes = total_original_bytes - total_compressed_bytes
    ratio = (saved_bytes / total_original_bytes) if total_original_bytes > 0 else 0.0

    # ── Compaction report JSON ─────────────────────────────────────────────────
    report: dict[str, Any] = {
        "date": date_str,
        "input_files": input_file_reports,
        "total_input_lines": total_input_lines,
        "unique_states": total_unique,
        "compressed_size_bytes": total_compressed_bytes,
        "compression_ratio": round(ratio, 4),
        "saved_bytes": saved_bytes,
        "archive_paths": archive_paths,
        "errors": errors,
        "dry_run": dry_run,
    }

    report_path = archive_day_dir / "compaction_report.json"
    if not dry_run:
        try:
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n  report: {report_path}")
        except OSError as e:
            errors.append(f"write report: {e}")

    # ── Daily summary + events JSONL + autobiography.md ──────────────────────
    if not dry_run:
        _write_daily_summary(date_str, daily_dir, file_stats, total_input_lines, total_unique, report)

    # ── Rename / delete originals ─────────────────────────────────────────────
    for stat in file_stats:
        if not stat.path.exists() or stat.lines == 0:
            continue
        if dry_run:
            action = "delete" if delete_originals else "rename to .compacted.bak"
            print(f"  [DRY-RUN] would {action}: {stat.path.name}")
        else:
            if delete_originals:
                try:
                    stat.path.unlink()
                    print(f"  [DELETED] {stat.path.name}")
                except OSError as e:
                    errors.append(f"delete {stat.path}: {e}")
            else:
                bak = stat.path.with_suffix(".compacted.bak")
                try:
                    shutil.move(str(stat.path), str(bak))
                    print(f"  [RENAMED] {stat.path.name} -> {bak.name}")
                except OSError as e:
                    errors.append(f"rename {stat.path}: {e}")

    report["errors"] = errors
    return report


# ---------------------------------------------------------------------------
# Daily summary helpers
# ---------------------------------------------------------------------------

def _write_daily_summary(
    date_str: str,
    daily_dir: Path,
    file_stats: list[_FileStats],
    total_input_lines: int,
    total_unique: int,
    report: dict[str, Any],
) -> None:
    """Write YYYY-MM-DD.summary.json, YYYY-MM-DD.events.jsonl, YYYY-MM-DD.autobiography.md."""

    # summary JSON
    summary: dict[str, Any] = {
        "date": date_str,
        "total_input_lines": total_input_lines,
        "unique_states": total_unique,
        "compression_ratio": report.get("compression_ratio", 0.0),
        "saved_bytes": report.get("saved_bytes", 0),
        "archive_paths": report.get("archive_paths", []),
    }
    summary_path = daily_dir / f"{date_str}.summary.json"
    try:
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    # events JSONL — one collapsed event per unique hash
    events_path = daily_dir / f"{date_str}.events.jsonl"
    try:
        with events_path.open("w", encoding="utf-8") as f:
            for stat in file_stats:
                for h, info in stat.dedup_map.items():
                    obj: dict[str, Any] = {
                        "semantic_hash": h,
                        "source": stat.path.name,
                        "count": info["count"],
                        "first_seen": info["first_seen"],
                        "last_seen": info["last_seen"],
                        "sample": info["sample_line"][:200],
                    }
                    f.write(json.dumps(obj, ensure_ascii=True) + "\n")
    except OSError:
        pass

    # autobiography markdown
    auto_md = _build_autobiography(date_str, file_stats, total_input_lines, total_unique)
    auto_path = daily_dir / f"{date_str}.autobiography.md"
    try:
        auto_path.write_text(auto_md, encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact and archive Latent Somatic runtime JSONL logs.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would happen; write nothing.")
    mode.add_argument("--apply", action="store_true", help="Apply compaction.")
    parser.add_argument(
        "--delete-originals",
        action="store_true",
        help="Delete original files after archiving (default: rename to .compacted.bak).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even if server.py appears to be running.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    print(f"\nSoma Log Compaction — {_today_str()}")
    print("=" * 50)

    if args.dry_run:
        print("[DRY RUN — no files will be written or modified]\n")

    report = compact(
        dry_run=args.dry_run,
        delete_originals=getattr(args, "delete_originals", False),
        force=getattr(args, "force", False),
    )

    print("\n" + "=" * 50)
    print(f"Total input lines : {report['total_input_lines']:,}")
    print(f"Unique states     : {report['unique_states']:,}")
    if not args.dry_run:
        print(f"Compression ratio : {report['compression_ratio']:.1%}")
        print(f"Saved bytes       : {_fmt_size(report['saved_bytes'])}")
    if report["errors"]:
        print(f"\nErrors ({len(report['errors'])}):")
        for e in report["errors"]:
            print(f"  - {e}")
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
