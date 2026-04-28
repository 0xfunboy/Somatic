from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


_EXCLUDE_DIRS = {".git", "__pycache__", "build", "logs", "weights", "models", "node_modules"}
_EXCLUDE_SUFFIXES = (".pt", ".pth", ".onnx", ".gguf", ".safetensors")
_EXCLUDE_FILE_NAMES = {".env"}


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
    ) -> None:
        self.repo_root = Path(repo_root)
        self.mutation_root = Path(mutation_root)
        self.ws_port = int(ws_port)
        self.http_port = int(http_port)
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
        return {"ok": True, "sandbox_path": str(sandbox_path), "mutation_id": mutation_id}

    def propose_mutation(self, context: dict) -> dict:
        proposal = {
            "mutation_id": uuid.uuid4().hex[:8],
            "objective": context.get("objective") or "Improve one Phase 8 reliability path in sandbox only.",
            "file_changes": context.get("file_changes", {}),
            "tests": context.get("tests", []),
        }
        self._last_status["proposal_generated"] = True
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
        return {"ok": ok, "changed_files": changed, "forbidden_files": forbidden}

    def run_tests(self, sandbox_path: Path) -> dict:
        commands = [
            "python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py",
            "python3 scripts/test_command_planner.py",
            "python3 scripts/test_telemetry_relevance.py",
            "python3 scripts/test_journal_compaction.py",
            "python3 scripts/test_actuation_dedupe.py",
            "python3 scripts/test_autobiography.py",
            "python3 scripts/test_nightly_reflection.py",
            "python3 scripts/test_self_improvement_workflow.py",
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
        return path

    def status(self) -> dict:
        self._last_status["sandbox_root_exists"] = self.mutation_root.exists()
        return dict(self._last_status)

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
