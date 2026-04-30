from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from soma_core.config import CFG


_REPO_ROOT = Path(__file__).parent.parent.resolve()
_PROMPT_PREVIEW_CHARS = max(200, int(getattr(CFG, "internal_event_preview_chars", 900) or 900))
_SUMMARY_STRING_CHARS = 400


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def estimate_json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def archive_prompt_text(text: str, data_root: Path | None = None, *, kind: str = "prompt") -> str:
    raw = str(text or "")
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
    archive_dir = root / "internal_prompts" / digest[:2]
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{digest}.{kind}.txt.gz"
    if not archive_path.exists():
        with gzip.open(archive_path, "wt", encoding="utf-8") as handle:
            handle.write(raw)
    return str(archive_path)


def prompt_preview(text: str, *, limit: int | None = None) -> str:
    size = max(120, int(limit or _PROMPT_PREVIEW_CHARS))
    return str(text or "")[:size]


def compact_prompt(
    prompt: str,
    data_root: Path | None = None,
    *,
    kind: str = "prompt",
    preview_chars: int | None = None,
) -> dict[str, Any]:
    text = str(prompt or "")
    if not text:
        return {"sha1": "", "preview": "", "chars": 0, "archive_path": ""}
    return {
        "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "preview": prompt_preview(text, limit=preview_chars),
        "chars": len(text),
        "archive_path": archive_prompt_text(text, data_root, kind=kind),
    }


def load_jsonl_tail(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    items: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)) :]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def append_jsonl_record(path: Path, record: dict[str, Any], *, max_lines: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    if max_lines > 0:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        if len(lines) > max_lines:
            trimmed = "\n".join(lines[-max_lines:])
            path.write_text(trimmed + ("\n" if trimmed else ""), encoding="utf-8")


def append_prompt_ledger_entry(data_root: Path | None, record: dict[str, Any]) -> Path:
    root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
    path = root / "internal_prompt_index.jsonl"
    append_jsonl_record(path, record, max_lines=max(100, int(CFG.internal_ledger_max_lines)))
    return path


def compact_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[compacted]"
    if isinstance(value, str):
        if len(value) <= _SUMMARY_STRING_CHARS:
            return value
        return {
            "preview": value[:_SUMMARY_STRING_CHARS],
            "chars": len(value),
            "sha1": hashlib.sha1(value.encode("utf-8")).hexdigest(),
        }
    if isinstance(value, list):
        items = [compact_json_value(item, depth=depth + 1) for item in value[:20]]
        if len(value) > 20:
            items.append({"truncated_items": len(value) - 20})
        return items
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 40:
                compacted["_truncated_keys"] = len(value) - 40
                break
            compacted[str(key)] = compact_json_value(item, depth=depth + 1)
        return compacted
    return value


def compact_mind_state_payload(name: str, payload: dict[str, Any], data_root: Path | None = None) -> dict[str, Any]:
    root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
    compacted: dict[str, Any] = {}
    prompt_fields = {
        "bios_state.json": {"last_internal_prompt": "bios_prompt", "last_raw": "bios_raw"},
        "internal_loop_state.json": {"last_prompt": "internal_prompt", "last_raw": "internal_raw"},
    }.get(name, {})
    for key, value in payload.items():
        if key in prompt_fields and isinstance(value, str):
            compacted[key] = compact_prompt(value, root, kind=prompt_fields[key])
            continue
        compacted[key] = compact_json_value(value)
    return compacted


def maybe_compact_json_state(
    path: Path,
    *,
    apply: bool = True,
    max_bytes: int | None = None,
    archive_dir: Path | None = None,
) -> dict[str, Any]:
    target_max = int(max_bytes or CFG.mind_state_max_bytes)
    original_exists = path.exists()
    original_bytes = path.stat().st_size if original_exists else 0
    payload = _load_json(path, {})
    if not isinstance(payload, dict):
        payload = {"payload": payload}
    compacted = compact_mind_state_payload(path.name, payload, path.parent)
    compacted_bytes = estimate_json_size(compacted)
    needs_apply = original_exists and (original_bytes > target_max or compacted_bytes < original_bytes)
    archived_to = ""
    if apply and needs_apply and original_exists:
        archive_root = archive_dir or (_REPO_ROOT / "data" / "archive" / "manual-pre-resource-governor")
        archive_root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        archived = archive_root / f"{path.name}.{stamp}.bak"
        shutil.copy2(path, archived)
        archived_to = str(archived)
        _save_json(path, compacted)
    return {
        "path": str(path),
        "applied": bool(apply and needs_apply and original_exists),
        "needs_apply": bool(needs_apply),
        "archived_to": archived_to,
        "original_bytes": int(original_bytes),
        "compacted_bytes": int(compacted_bytes),
        "before_over_limit": original_bytes > target_max,
        "after_over_limit": compacted_bytes > target_max,
    }
