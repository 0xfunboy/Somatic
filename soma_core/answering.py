from __future__ import annotations

import re
from typing import Any

from soma_core.output_filter import OutputFilter


def _is_italian(text: str) -> bool:
    low = (text or "").lower()
    markers = (
        " che ", " quale ", " quali ", " come ", " non ", " hai ", " mio ", " tuoi ", " lezioni ",
        " controlla ", " esegui ", " verifica ", " comando ", " pubblico ", " versione ", " kernel ",
    )
    return any(mark in f" {low} " for mark in markers) or any(tok in low for tok in ("perché", "qual", "versione", "pubblico"))


def _clean_single_line(text: str, limit: int = 400) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:limit].rstrip()


class AnswerFinalizer:
    def __init__(self, output_filter: OutputFilter | None = None) -> None:
        self._filter = output_filter or OutputFilter()

    def finalize(
        self,
        user_text: str,
        snapshot: dict[str, Any],
        *,
        command_result: dict[str, Any] | None = None,
        skill_result: dict[str, Any] | None = None,
        llm_text: str | None = None,
    ) -> str:
        italian = _is_italian(user_text)
        if command_result is not None:
            if command_result.get("ok") is True:
                text = self._command_success_text(command_result, italian)
                return self._filter.clean_response(
                    text,
                    user_text,
                    snapshot,
                    command_result=command_result,
                    skill_result=skill_result,
                )
            text = self._command_failure_text(command_result, italian)
            return self._filter.clean_response(
                text,
                user_text,
                snapshot,
                command_result=command_result,
                skill_result=skill_result,
            )

        if skill_result is not None and skill_result.get("ok") is True:
            text = self._skill_success_text(skill_result, italian)
            return self._filter.clean_response(
                text,
                user_text,
                snapshot,
                skill_result=skill_result,
            )

        if skill_result is not None and skill_result.get("ok") is False:
            text = self._skill_failure_text(skill_result, italian)
            return self._filter.clean_response(text, user_text, snapshot, skill_result=skill_result)

        if llm_text:
            return self._filter.clean_response(llm_text, user_text, snapshot)

        return self._filter.clean_response(
            "Non ho abbastanza contesto operativo per rispondere con certezza. Posso verificare con un comando se la richiesta è misurabile."
            if italian else
            "I do not have enough verified operational context to answer that with confidence. I can verify it with a command if it is measurable.",
            user_text,
            snapshot,
        )

    def _command_success_text(self, result: dict[str, Any], italian: bool) -> str:
        cmd = str(result.get("cmd") or "command")
        stdout = _clean_single_line(str(result.get("stdout") or ""))
        if stdout:
            return (
                f"Ho verificato con `{cmd}`: {stdout}."
                if italian else
                f"I verified with `{cmd}`: {stdout}."
            )
        return (
            f"Ho eseguito `{cmd}`: successo, ma non ha prodotto output."
            if italian else
            f"I ran `{cmd}` successfully, but it produced no output."
        )

    def _command_failure_text(self, result: dict[str, Any], italian: bool) -> str:
        cmd = str(result.get("cmd") or "command")
        err = _clean_single_line(str(result.get("stderr") or result.get("stdout") or "errore non specificato"))
        next_step = self._next_step_for_command(cmd, italian)
        return (
            f"Ho provato `{cmd}`, ma è fallito: {err}. Prossimo controllo: {next_step}."
            if italian else
            f"I tried `{cmd}`, but it failed: {err}. Next check: {next_step}."
        )

    def _skill_success_text(self, result: dict[str, Any], italian: bool) -> str:
        text = _clean_single_line(str(result.get("text") or result.get("stdout") or ""))
        if text:
            return text
        skill_id = str(result.get("skill_id") or result.get("id") or "skill")
        return (
            f"Ho eseguito lo skill `{skill_id}` con successo, ma senza output."
            if italian else
            f"I executed the `{skill_id}` skill successfully, but it produced no output."
        )

    def _skill_failure_text(self, result: dict[str, Any], italian: bool) -> str:
        skill_id = str(result.get("skill_id") or result.get("id") or "skill")
        err = _clean_single_line(str(result.get("stderr") or result.get("text") or "errore non specificato"))
        return (
            f"Lo skill `{skill_id}` non è riuscito: {err}."
            if italian else
            f"The `{skill_id}` skill failed: {err}."
        )

    def _next_step_for_command(self, cmd: str, italian: bool) -> str:
        low = cmd.lower()
        if "curl" in low and "ifconfig.me" in low:
            return "verificare connettività DNS e accesso HTTP in uscita" if italian else "verify DNS connectivity and outbound HTTP access"
        if "node" in low:
            return "controllare che `node` sia nel PATH" if italian else "check that `node` is available in PATH"
        if "runtime_storage_report.py" in low or "du -sh data/" in low:
            return "verificare che i percorsi locali `data/`, `logs/` e `data/journal/` esistano" if italian else "verify that local `data/`, `logs/`, and `data/journal/` paths exist"
        return "ripetere il controllo manualmente con lo stesso comando" if italian else "rerun the same command manually for verification"
