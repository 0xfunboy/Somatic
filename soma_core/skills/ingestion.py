"""Skill ingestion manager — import, quarantine, enable/disable OpenClaw skills."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from soma_core.skills.openclaw_adapter import OpenClawSkillAdapter
from soma_core.skills.validation import assess_risk

if TYPE_CHECKING:
    from soma_core.skills.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# soma_core/skills/ingestion.py → parent=skills/ → parent=soma_core/ → parent=repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

_IMPORTED_DIR = _REPO_ROOT / "skills" / "imported" / "openclaw"
_QUARANTINE_DIR = _REPO_ROOT / "skills" / "quarantine" / "openclaw"
_DATA_DIR = _REPO_ROOT / "data" / "skills"
_IMPORTED_FILE = _DATA_DIR / "imported_openclaw_skills.json"
_INGESTION_HISTORY = _DATA_DIR / "ingestion_history.jsonl"
_QUARANTINE_LOG = _DATA_DIR / "quarantine.jsonl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    for d in (_IMPORTED_DIR, _QUARANTINE_DIR, _DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_imported() -> dict[str, Any]:
    """Load the imported skills JSON store, returning a dict keyed by skill_id."""
    if not _IMPORTED_FILE.exists():
        return {}
    try:
        raw = _IMPORTED_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_imported(store: dict[str, Any]) -> None:
    """Atomically write the imported skills JSON store."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _IMPORTED_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_IMPORTED_FILE)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _emit_trace(trace: Any, event: str, message: str, **kwargs: Any) -> None:
    if trace is None:
        return
    try:
        trace.emit(event, message, **kwargs)
    except Exception:
        pass


def _emit_journal(journal: Any, record: dict[str, Any]) -> None:
    if journal is None:
        return
    try:
        journal.append(record)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SkillIngestionManager
# ---------------------------------------------------------------------------


class SkillIngestionManager:
    """Manages the lifecycle of imported OpenClaw skills.

    Responsibilities:
    - Parse skill folders via :class:`~soma_core.skills.openclaw_adapter.OpenClawSkillAdapter`
    - Run risk assessment and route to imported or quarantine directories
    - Persist state to ``data/skills/imported_openclaw_skills.json`` and JSONL logs
    - Register non-quarantined skills in the :class:`~soma_core.skills.registry.SkillRegistry`
    - Expose enable / disable / quarantine controls
    """

    def __init__(
        self,
        registry: "SkillRegistry",
        autobiography: Any = None,
        journal: Any = None,
        trace: Any = None,
    ) -> None:
        self._registry = registry
        self._autobiography = autobiography
        self._journal = journal
        self._trace = trace
        self._adapter = OpenClawSkillAdapter()
        _ensure_dirs()

    # ------------------------------------------------------------------
    # Import a single skill folder
    # ------------------------------------------------------------------

    def import_skill(self, path: Path) -> dict[str, Any]:
        """Import a single OpenClaw skill folder at *path*.

        Returns a report dict with keys: skill_id, status, quarantined,
        destination, warnings, risk_level, reasons.
        """
        path = Path(path)
        report: dict[str, Any] = {
            "skill_id": None,
            "status": "failed",
            "quarantined": False,
            "destination": None,
            "warnings": [],
            "risk_level": "low",
            "reasons": [],
        }

        # 1. Parse the skill folder
        try:
            skill = self._adapter.load_folder(path)
        except Exception as exc:
            report["status"] = "failed"
            report["warnings"].append(f"load_folder failed: {exc}")
            return report

        report["skill_id"] = skill.id

        # 2. Run risk assessment
        assessment = assess_risk(skill.instructions, list(skill.permissions), {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "risk_level": skill.risk_level,
        })
        report["risk_level"] = assessment["risk_level"]
        report["reasons"] = assessment["reasons"]

        # Override skill fields from assessment
        skill.risk_level = assessment["risk_level"]  # type: ignore[assignment]
        skill.requires_confirmation = assessment["requires_confirmation"]
        if assessment["quarantine"]:
            skill.quarantine_reason = "; ".join(assessment["reasons"])
            skill.enabled = False

        # 3. Copy folder to imported or quarantine destination
        store = _load_imported()
        quarantined = assessment["quarantine"]

        if quarantined:
            dest_dir = _QUARANTINE_DIR / skill.id
            event_phase = "openclaw_skill_quarantined"
        else:
            dest_dir = _IMPORTED_DIR / skill.id
            event_phase = "openclaw_skill_imported"

        try:
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(str(path), str(dest_dir))
            report["destination"] = str(dest_dir)
        except Exception as exc:
            report["warnings"].append(f"copytree failed: {exc}")
            # Continue — we still record and register even without copy

        # 4. Update imported_openclaw_skills.json
        skill.source_path = str(dest_dir)
        skill.imported_at = time.time()
        entry: dict[str, Any] = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "risk_level": skill.risk_level,
            "permissions": list(skill.permissions),
            "enabled": skill.enabled,
            "quarantined": quarantined,
            "quarantine_reason": skill.quarantine_reason,
            "requires_confirmation": skill.requires_confirmation,
            "source_path": str(dest_dir),
            "imported_at": skill.imported_at,
        }
        store[skill.id] = entry
        _save_imported(store)

        # 5. Append to ingestion_history.jsonl
        _append_jsonl(_INGESTION_HISTORY, {
            "ts": time.time(),
            "skill_id": skill.id,
            "status": "quarantined" if quarantined else "imported",
            "risk_level": assessment["risk_level"],
            "reasons": assessment["reasons"],
            "source_path": str(path),
            "destination": str(dest_dir),
        })

        # 6. Emit trace event
        _emit_trace(
            self._trace,
            event_phase,
            f"{'Quarantined' if quarantined else 'Imported'} skill: {skill.id}",
            inputs={"skill_id": skill.id, "source": str(path)},
            outputs={"risk_level": assessment["risk_level"], "quarantined": quarantined},
            level="warning" if quarantined else "info",
        )

        # 7. Register in registry if not quarantined
        if not quarantined:
            self._registry.register(skill)
            report["status"] = "imported"
        else:
            report["status"] = "quarantined"
            report["quarantined"] = True

        report["warnings"] += self._adapter.validate_skill(skill)
        return report

    # ------------------------------------------------------------------
    # Bulk import
    # ------------------------------------------------------------------

    def import_all(self, root: Path) -> dict[str, Any]:
        """Import all skill sub-folders under *root* that contain a SKILL.md.

        Returns a summary dict: total, imported, quarantined, failed, results.
        """
        root = Path(root)
        results: list[dict[str, Any]] = []
        total = imported = quarantined = failed = 0

        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            if not (folder / "SKILL.md").exists():
                continue
            total += 1
            try:
                result = self.import_skill(folder)
                results.append(result)
                if result["status"] == "imported":
                    imported += 1
                elif result["status"] == "quarantined":
                    quarantined += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                results.append({
                    "skill_id": folder.name,
                    "status": "failed",
                    "quarantined": False,
                    "warnings": [str(exc)],
                })

        return {
            "total": total,
            "imported": imported,
            "quarantined": quarantined,
            "failed": failed,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, skill_id: str) -> dict[str, Any]:
        """Enable a previously imported skill.

        Returns ``{"ok": bool, "skill_id": skill_id}``.
        """
        store = _load_imported()
        if skill_id not in store:
            return {"ok": False, "skill_id": skill_id, "error": "skill not found in store"}

        entry = store[skill_id]
        if entry.get("quarantined"):
            return {
                "ok": False,
                "skill_id": skill_id,
                "error": "skill is quarantined — use unquarantine() first",
            }

        entry["enabled"] = True
        store[skill_id] = entry
        _save_imported(store)

        # Update registry
        skill = self._registry.get(skill_id)
        if skill is not None:
            skill.enabled = True

        return {"ok": True, "skill_id": skill_id}

    def disable(self, skill_id: str) -> dict[str, Any]:
        """Disable an imported skill without quarantining it.

        Returns ``{"ok": bool, "skill_id": skill_id}``.
        """
        store = _load_imported()
        if skill_id not in store:
            return {"ok": False, "skill_id": skill_id, "error": "skill not found in store"}

        store[skill_id]["enabled"] = False
        _save_imported(store)

        # Update registry
        skill = self._registry.get(skill_id)
        if skill is not None:
            skill.enabled = False

        return {"ok": True, "skill_id": skill_id}

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    def quarantine(self, skill_id: str, reason: str) -> dict[str, Any]:
        """Move an imported skill to quarantine and mark it disabled.

        Returns ``{"ok": bool, "skill_id": skill_id, "reason": reason}``.
        """
        store = _load_imported()
        if skill_id not in store:
            return {"ok": False, "skill_id": skill_id, "error": "skill not found in store"}

        entry = store[skill_id]
        src_dir = Path(entry.get("source_path", ""))
        dest_dir = _QUARANTINE_DIR / skill_id

        # Move from imported to quarantine directory (best effort)
        if src_dir.exists() and src_dir != dest_dir:
            try:
                if dest_dir.exists():
                    shutil.rmtree(dest_dir)
                shutil.move(str(src_dir), str(dest_dir))
                entry["source_path"] = str(dest_dir)
            except Exception:
                pass  # non-fatal — still update the metadata

        entry["enabled"] = False
        entry["quarantined"] = True
        entry["quarantine_reason"] = reason
        store[skill_id] = entry
        _save_imported(store)

        # Disable in registry
        skill = self._registry.get(skill_id)
        if skill is not None:
            skill.enabled = False
            skill.quarantine_reason = reason

        # Append to quarantine log
        _append_jsonl(_QUARANTINE_LOG, {
            "ts": time.time(),
            "skill_id": skill_id,
            "reason": reason,
        })

        _emit_trace(
            self._trace,
            "openclaw_skill_quarantined",
            f"Skill manually quarantined: {skill_id}",
            inputs={"skill_id": skill_id, "reason": reason},
            outputs={"quarantined": True},
            level="warning",
        )

        return {"ok": True, "skill_id": skill_id, "reason": reason}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a summary of all tracked imported/quarantined skills."""
        store = _load_imported()
        total_imported = len(store)
        enabled = sum(1 for e in store.values() if e.get("enabled") and not e.get("quarantined"))
        quarantined = sum(1 for e in store.values() if e.get("quarantined"))
        failed = sum(
            1 for e in store.values()
            if not e.get("enabled") and not e.get("quarantined")
        )
        return {
            "total_imported": total_imported,
            "enabled": enabled,
            "quarantined": quarantined,
            "failed": failed,
        }
