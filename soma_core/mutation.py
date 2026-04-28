from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from soma_core.config import CFG


_EXCLUDE_DIRS = {".git", "__pycache__", "build", "logs", "weights", "models", "node_modules"}
_EXCLUDE_SUFFIXES = (".pt", ".pth", ".onnx", ".gguf", ".safetensors")
_EXCLUDE_FILE_NAMES = {".env"}
_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def _is_excluded(path: Path) -> bool:
    rel = path.as_posix()
    if path.name in _EXCLUDE_FILE_NAMES:
        return True
    if any(part in _EXCLUDE_DIRS for part in path.parts):
        return True
    if rel.startswith("data/mind/") and rel.endswith(".jsonl"):
        return True
    if rel.startswith("data/runtime/") and rel.endswith(".jsonl"):
        return True
    if rel.startswith("data/journal/hot/") and rel.endswith(".jsonl"):
        return True
    if rel.startswith("data/archive/"):
        return True
    if path.suffix.lower() in _EXCLUDE_SUFFIXES:
        return True
    return False


class MutationSandbox:
    def __init__(
        self,
        *,
        repo_root: str | Path = "/home/funboy/latent-somatic",
        mutation_root: str | Path = "/home/funboy/latent-somatic-mutants",
        ws_port: int = 8875,
        http_port: int = 8880,
        power_policy: Any = None,
        reward_engine: Any = None,
        autobiography: Any = None,
        experience: Any = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.mutation_root = Path(mutation_root)
        self.ws_port = int(ws_port)
        self.http_port = int(http_port)
        self._power_policy = power_policy
        self._reward_engine = reward_engine
        self._autobiography = autobiography
        self._experience = experience
        self._reports_dir = _REPO_ROOT / "data" / "mind" / "mutations"
        self._reports_index_path = self._reports_dir / "reports.jsonl"
        self._state_path = _REPO_ROOT / "data" / "mind" / "mutation_state.json"
        self._last_status: dict[str, Any] = {
            "enabled": True,
            "sandbox_root_exists": self.mutation_root.exists(),
            "sandbox_count": 0,
            "last_sandbox": "",
            "last_report": "",
            "candidate_available": False,
            "recommendation": "",
            "proposal_generated": False,
            "sandbox_only": True,
            "operator_approval_required": True,
            "last_noop_ok": False,
            "rollback_ok": False,
            "last_tests_ok": False,
            "last_diff_summary": "",
            "full_validation_ok": False,
            "last_blockers": [],
            "last_decision": "",
        }

    def create_sandbox(self, reason: str) -> dict:
        mutation_id = uuid.uuid4().hex[:8]
        sandbox_path = self.mutation_root / f"{_now_stamp()}-{mutation_id}"
        self.mutation_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.repo_root,
            sandbox_path,
            ignore=self._ignore_callback,
            dirs_exist_ok=False,
        )
        manifest = {
            "mutation_id": mutation_id,
            "created_at": time.time(),
            "reason": reason,
            "repo_root": str(self.repo_root),
        }
        (sandbox_path / "mutation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (sandbox_path / "MUTATION_REPORT.md").write_text("# Mutation Report\n\nPending evaluation.\n", encoding="utf-8")
        self._last_status.update({
            "sandbox_root_exists": True,
            "sandbox_count": int(self._last_status.get("sandbox_count", 0)) + 1,
            "last_sandbox": str(sandbox_path),
            "last_noop_ok": True,
        })
        self._persist_status()
        return {"ok": True, "sandbox_path": str(sandbox_path), "mutation_id": mutation_id}

    def propose_mutation(self, context: dict) -> dict:
        proposal = {
            "mutation_id": uuid.uuid4().hex[:8],
            "objective": context.get("objective") or "Improve one Phase 8 reliability path in sandbox only.",
            "file_changes": context.get("file_changes", {}),
            "tests": context.get("tests", []),
        }
        self._last_status["proposal_generated"] = True
        self._persist_status()
        return proposal

    def apply_mutation_to_sandbox(self, sandbox_path: Path, proposal: dict) -> dict:
        forbidden: list[str] = []
        changed: list[str] = []
        for rel_path, new_content in (proposal.get("file_changes") or {}).items():
            rel = Path(rel_path)
            if _is_excluded(rel):
                forbidden.append(rel_path)
                continue
            full = (sandbox_path / rel).resolve()
            if not str(full).startswith(str(sandbox_path.resolve())):
                forbidden.append(rel_path)
                continue
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(str(new_content), encoding="utf-8")
            changed.append(rel_path)
        ok = not forbidden
        self._last_status["last_diff_summary"] = f"{len(changed)} sandbox file(s) changed"
        self._persist_status()
        return {"ok": ok, "changed_files": changed, "forbidden_files": forbidden}

    def run_tests(self, sandbox_path: Path) -> dict:
        commands = [
            "python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py",
            "python3 scripts/test_metabolism.py",
            "python3 scripts/test_internal_loop.py",
            "python3 scripts/test_reward_engine.py",
            "python3 scripts/test_power_policy.py",
            "python3 scripts/test_vector_interpreter.py",
            "python3 scripts/test_growth_recovery_switch.py",
            "python3 scripts/test_mutation_reward.py",
            "python3 scripts/test_phase9_introspection.py",
            "python3 scripts/test_answer_finalizer.py",
            "python3 scripts/test_output_filter.py",
            "python3 scripts/test_relevance_filter.py",
            "python3 scripts/test_growth_engine.py",
            "python3 scripts/test_baselines.py",
            "python3 scripts/test_bios_loop.py",
            "python3 scripts/test_mutation_sandbox.py",
            "python3 scripts/test_cpp_bridge.py",
            "python3 scripts/test_life_drive.py",
            "python3 scripts/test_experience_distiller.py",
            "python3 scripts/test_command_planner.py",
            "python3 scripts/test_telemetry_relevance.py",
            "python3 scripts/test_phase8_regressions.py",
        ]
        results: list[dict[str, Any]] = []
        ok = True
        for cmd in commands:
            result = subprocess.run(cmd, shell=True, cwd=str(sandbox_path), capture_output=True, text=True, timeout=180)
            item = {
                "cmd": cmd,
                "ok": result.returncode == 0,
                "stdout": (result.stdout or "")[:500],
                "stderr": (result.stderr or "")[:300],
            }
            results.append(item)
            ok = ok and item["ok"]
        self._last_status["last_tests_ok"] = ok
        self._persist_status()
        return {"ok": ok, "results": results}

    def run_smoke_test(self, sandbox_path: Path) -> dict:
        env = {
            **os.environ,
            "SOMA_WS_PORT": str(self.ws_port),
            "SOMA_HTTP_PORT": str(self.http_port),
            "SOMA_SENSOR_PROVIDER": "mock",
            "SOMA_LLM_MODE": "off",
        }
        proc = subprocess.Popen(
            ["python3", "server.py"],
            cwd=str(sandbox_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            time.sleep(5)
            if proc.poll() is not None:
                return {"ok": False, "running": False}
            smoke = subprocess.run(
                ["python3", "scripts/ws_smoke_test.py", "--host", "127.0.0.1", "--port", str(self.ws_port), "--timeout", "20"],
                cwd=str(sandbox_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "ok": smoke.returncode == 0,
                "running": proc.poll() is None,
                "stdout": (smoke.stdout or "")[:500],
                "stderr": (smoke.stderr or "")[:300],
            }
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def evaluate_mutation(self, sandbox_path: Path, proposal: dict, test_result: dict) -> dict:
        recommendation = "candidate_for_migration" if test_result.get("ok") else "reject"
        report = {
            "sandbox_path": str(sandbox_path),
            "proposal": proposal,
            "test_result": test_result,
            "recommendation": recommendation if recommendation != "candidate_for_migration" else "keep_for_review",
            "operator_approval_required": True,
        }
        self._last_status["recommendation"] = report["recommendation"]
        self._persist_status()
        return report

    def write_report(self, report: dict) -> Path:
        sandbox_path = Path(report["sandbox_path"])
        path = sandbox_path / "MUTATION_REPORT.md"
        lines = [
            "# Mutation Report",
            "",
            f"Recommendation: {report.get('recommendation')}",
            "",
            "## Proposal",
            json.dumps(report.get("proposal", {}), indent=2, ensure_ascii=False),
            "",
            "## Test Result",
            json.dumps(report.get("test_result", {}), indent=2, ensure_ascii=False),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        self._last_status["last_report"] = str(path)
        self._persist_status()
        return path

    def status(self) -> dict:
        self._last_status["sandbox_root_exists"] = self.mutation_root.exists()
        self._persist_status()
        return dict(self._last_status)

    def can_mutate(self, metabolic: dict, growth: dict, reward: dict) -> tuple[bool, list[str]]:
        blockers: list[str] = []
        calibrated_conf = float(
            metabolic.get("sensor_confidence_calibrated", metabolic.get("sensor_confidence", 0.0)) or 0.0
        )
        if calibrated_conf < 0.55:
            blockers.append("low_calibrated_sensor_confidence")
        if not metabolic.get("growth_allowed", False):
            blockers.append("growth_not_allowed")
        if metabolic.get("recovery_required", False):
            blockers.append("recovery_required")
        if float(metabolic.get("self_integrity", 0.0) or 0.0) < CFG.min_self_integrity:
            blockers.append("self_integrity_below_min")
        if self._last_status.get("last_tests_ok") is False and self._last_status.get("sandbox_count", 0):
            blockers.append("recent_tests_failing")
        if int(self._last_status.get("sandbox_count", 0)) >= CFG.mutation_max_per_day:
            blockers.append("daily_mutation_limit_reached")
        if float(reward.get("rolling_score", 0.0) or 0.0) < -0.25:
            blockers.append("reward_trend_negative")
        if growth.get("recovery_required"):
            blockers.append("growth_engine_reports_recovery")
        self._last_status["last_blockers"] = blockers
        self._persist_status()
        return not blockers, blockers

    def create_child_if_allowed(
        self,
        reason: str,
        metabolic: dict,
        *,
        growth: dict | None = None,
        reward: dict | None = None,
    ) -> dict:
        allowed, blockers = self.can_mutate(metabolic, growth or {}, reward or {})
        if not allowed:
            return {"ok": False, "summary": f"mutation blocked: {', '.join(blockers)}", "blockers": blockers}
        result = self.create_sandbox(reason)
        if result.get("ok"):
            self._last_status["candidate_available"] = True
            self._last_status["last_decision"] = "sandbox_created"
            self._persist_status()
        return result

    def evaluate_with_reward(
        self,
        sandbox_path: Path,
        proposal: dict,
        test_result: dict,
        metabolic_before: dict,
        metabolic_after: dict,
        reward_before: dict,
        reward_after: dict,
    ) -> dict:
        reward_delta = float(reward_after.get("rolling_score", 0.0) or 0.0) - float(reward_before.get("rolling_score", 0.0) or 0.0)
        stress_delta = float(metabolic_after.get("stress", 0.0) or 0.0) - float(metabolic_before.get("stress", 0.0) or 0.0)
        power_gain = proposal.get("objective") or proposal.get("expected_power_gain") or "sandbox validation"
        allowed, reasons = self._power_policy.allowed(proposal) if self._power_policy is not None else (True, [])
        decision = "reject"
        blockers: list[str] = []
        if not allowed:
            blockers.extend(reasons)
        if not test_result.get("ok"):
            blockers.append("tests_failed")
        if stress_delta > 0.08:
            blockers.append("stress_increased")
        if not blockers and reward_delta >= CFG.reward_min_for_mutation_keep:
            decision = "candidate_for_migration" if test_result.get("full_validation_ok") else "keep_for_review"
        elif not blockers and test_result.get("ok"):
            decision = "keep_for_review"
        else:
            decision = "reject"

        report = {
            "mutation_id": proposal.get("mutation_id") or uuid.uuid4().hex[:8],
            "parent_repo": str(self.repo_root),
            "child_repo": str(sandbox_path),
            "sandbox_path": str(sandbox_path),
            "proposal": proposal,
            "tests": test_result,
            "smoke": test_result.get("smoke") or {},
            "metabolic_before": metabolic_before,
            "metabolic_after": metabolic_after,
            "reward_before": reward_before,
            "reward_after": reward_after,
            "power_gain": power_gain,
            "risk": proposal.get("risk", "unknown"),
            "decision": decision,
            "blockers": blockers,
            "operator_approval_required": True,
        }
        reward_event = None
        if self._reward_engine is not None:
            reward_event = self._reward_engine.mutation_reward(
                metabolic_before,
                {
                    **metabolic_after,
                    "tests_ok": bool(test_result.get("ok")),
                    "rolled_back": decision == "reject",
                    "last_tests_ok": bool(test_result.get("ok")),
                },
            )
        report["reward"] = reward_event or {}
        self._persist_report(report)
        self._last_status.update(
            {
                "recommendation": decision,
                "last_report": str((sandbox_path / "MUTATION_REPORT.md").resolve()),
                "last_decision": decision,
                "last_blockers": blockers,
                "candidate_available": decision in {"keep_for_review", "candidate_for_migration"},
                "full_validation_ok": bool(test_result.get("full_validation_ok")),
            }
        )
        self.write_report(report)
        self._persist_status()
        if decision == "reject":
            self._write_rejection_lesson(report)
        return report

    def latest_reports(self, limit: int = 5) -> list[dict]:
        reports: list[dict] = []
        try:
            lines = self._reports_index_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        for line in lines[-max(1, limit) :]:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                reports.append(payload)
        return reports

    def _ignore_callback(self, _src: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        src_path = Path(_src)
        for name in names:
            try:
                rel = (src_path / name).resolve().relative_to(self.repo_root.resolve())
            except Exception:
                rel = Path(name)
            if _is_excluded(rel):
                ignored.add(name)
        return ignored

    def _persist_status(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(self._last_status, indent=2, ensure_ascii=False), encoding="utf-8")

    def _persist_report(self, report: dict[str, Any]) -> None:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        with self._reports_index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False) + "\n")

    def _write_rejection_lesson(self, report: dict[str, Any]) -> None:
        summary = f"Rejected mutation {report.get('mutation_id')} because: {', '.join(report.get('blockers', []) or ['unknown_reason'])}."
        if self._autobiography is not None:
            try:
                self._autobiography.write_meaningful_event({
                    "kind": "mutation",
                    "title": "Mutation rejected during evaluation",
                    "summary": summary[:300],
                    "impact": "high",
                    "timestamp": time.time(),
                })
            except Exception:
                pass
        if self._experience is not None:
            try:
                self._experience.save_lessons([
                    {
                        "id": f"mutation.reject.{report.get('mutation_id')}",
                        "kind": "mutation_lesson",
                        "observation": summary[:240],
                        "behavioral_update": "Reject sandbox mutations that increase stress or fail validation.",
                        "evidence": [{"report": report.get("decision"), "blockers": report.get("blockers", [])}],
                        "confidence": 0.9,
                        "created_at": time.time(),
                        "last_confirmed_at": time.time(),
                        "confirmations": 1,
                    }
                ])
            except Exception:
                pass
