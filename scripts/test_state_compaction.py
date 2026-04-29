#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.state_compaction import maybe_compact_json_state


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    failures = 0
    prompt = "PROMPT_BLOCK_" + ("A" * 3_000_000)
    raw = "RAW_BLOCK_" + ("B" * 600_000)
    parsed = {"action_type": "observe", "reason": "preserve parsed JSON", "nested": {"ok": True, "n": 3}}

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "internal_loop_state.json"
        payload = {
            "last_prompt": prompt,
            "last_raw": raw,
            "last_parsed": parsed,
            "last_parsed_fallback": {},
            "last_evidence": {"reason": "still keep compact evidence"},
        }
        write_json(path, payload)
        result = maybe_compact_json_state(path, apply=True, max_bytes=64 * 1024, archive_dir=root / "archive")
        compacted = json.loads(path.read_text(encoding="utf-8"))
        prompt_ref = compacted.get("last_prompt", {})

        failures += check("3mb internal state compacts under 64kb", path.stat().st_size < 64 * 1024, str(result))
        failures += check(
            "full prompt archived with hash preserved",
            prompt_ref.get("sha1") == hashlib.sha1(prompt.encode("utf-8")).hexdigest() and Path(str(prompt_ref.get("archive_path") or "")).exists(),
            str(prompt_ref),
        )
        failures += check("parsed json preserved", compacted.get("last_parsed") == parsed, str(compacted.get("last_parsed")))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "internal_loop_state.json"
        payload = {"last_prompt": prompt, "last_raw": raw, "last_parsed": parsed}
        write_json(path, payload)
        before = path.read_text(encoding="utf-8")
        result = maybe_compact_json_state(path, apply=False, max_bytes=64 * 1024, archive_dir=root / "archive")
        after = path.read_text(encoding="utf-8")
        failures += check("dry run changes nothing", before == after and result["applied"] is False and result["needs_apply"] is True, str(result))
    return failures


if __name__ == "__main__":
    sys.exit(main())
