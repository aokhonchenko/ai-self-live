#!/usr/bin/env python3
"""Run the local minimal ai-lives agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.file_tools import TOOL_PASSPORT, TOOL_SCHEMAS, ToolError, call_tool, tool_result_json
from scripts.llm_client import LlmClientError, OpenAICompatibleClient


DEFAULT_SETTINGS = {
    "step_limit": 300,
    "request_timeout_seconds": 300,
    "repeated_tool_error_limit": 3,
    "repeated_tool_call_limit": 3,
    "temperature": 0.2,
}


class AgentError(RuntimeError):
    """Raised when the local agent cannot complete a session."""


@dataclass(frozen=True)
class ToolExecutionBatch:
    messages: list[dict[str, Any]]
    error_signatures: list[str]
    call_signatures: list[str]
    final: str | None = None


def diagnostic(message: str) -> None:
    """Print a diagnostic message prefixed with [agent] to stdout."""
    print(f"[agent] {message}", flush=True)


def read_settings(path: Path) -> dict[str, Any]:
    """Load agent settings from a TOML file, merging with defaults."""
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    settings = dict(DEFAULT_SETTINGS)
    settings.update(data.get("agent", {}))
    return settings


def read_task(prompt_file: Path) -> str:
    """Read the session prompt from a file."""
    if not prompt_file.exists():
        raise AgentError(f"Prompt file does not exist: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8")


def system_message(tool_passport: str = TOOL_PASSPORT) -> str:
    """Build the system prompt for the ai-lives agent from a tool passport."""
    return f"""Ты локальный автономный агент проекта ai-lives.

Работай только через инструменты, перечисленные в этом паспорте. Паспорт генерируется из директорий `src/tools/*/tool.py`, поэтому не вызывай инструменты, которых нет в списке.

{tool_passport}

Для существующих файлов предпочитай точечные инструменты чтения и правки вместо полной перезаписи.

Если инструмент вернул `ok:false`, это не системная ошибка, а наблюдение о реальном состоянии файлов.
Скорректируй план: создай недостающий файл, выбери другой путь или явно зафиксируй отсутствие.

Если нужен новый инструмент, создай отдельную директорию `src/tools/<tool_name>/` с `tool.py`,
но в текущей сессии пользуйся только уже выданными инструментами из паспорта.

Обязательные результаты каждой успешной сессии:
1. Обновить state/last_session.md.
2. Добавить запись в logs/history.md.
3. Если менялся план, обновить state/current_plan.md.

Все пользовательские артефакты пиши на русском языке. Для завершения ответь обычным финальным
сообщением без вызова инструментов. Не вызывай инструмент `final`: такого инструмента нет.
Если endpoint не поддерживает tool calling, можно вернуть ровно JSON-объект одного из видов:
{{"tool":"имя_инструмента","аргумент":"значение"}}
{{"final":"краткий итог"}}
"""

def initial_messages(task: str) -> list[dict[str, Any]]:
    """Build the initial system + user message list for a session."""
    return [
        {"role": "system", "content": system_message()},
        {"role": "user", "content": task},
    ]


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    """Parse a JSON string of tool arguments, raising AgentError on invalid input."""
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise AgentError(f"tool arguments are not valid JSON: {raw}") from exc
    if not isinstance(parsed, dict):
        raise AgentError("tool arguments must be a JSON object")
    return parsed


def assistant_message_for_history(message: dict[str, Any]) -> dict[str, Any]:
    """Convert an LLM response message into a history-compatible dict."""
    stored = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        stored["tool_calls"] = message["tool_calls"]
    return stored


def compact_string(value: str) -> str | dict[str, Any]:
    """Compact a string for history: return as-is if short, or a summary dict."""
    if len(value) <= 200:
        return value
    encoded = value.encode("utf-8")
    return {
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest()[:12],
        "preview": value[:80],
    }


def compact_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Compact tool arguments for history, special-casing write_file content."""
    if name == "write_file":
        content = str(arguments.get("content", ""))
        return {
            "path": str(arguments.get("path", "")),
            "content_bytes": len(content.encode("utf-8")),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()[:12],
        }
    return {key: compact_string(value) if isinstance(value, str) else value for key, value in arguments.items()}


def tool_call_signature(name: str, arguments: dict[str, Any]) -> str:
    """Build a JSON signature string for a tool call (for deduplication)."""
    payload = {"tool": name, "arguments": compact_tool_arguments(name, arguments)}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def tool_observation(name: str, ok: bool, payload: dict[str, Any] | str) -> str:
    """Build a JSON observation string for a tool execution result."""
    if ok:
        return tool_result_json({"tool": name, "ok": True, "result": payload})
    return tool_result_json({"tool": name, "ok": False, "error": str(payload)})


def execute_native_tool_calls(root: Path, message: dict[str, Any]) -> ToolExecutionBatch:
    """Execute tool_calls from an LLM message using native JSON-RPC-style calls."""
    results = []
    error_signatures = []
    call_signatures = []
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        name = function.get("name", "")
        try:
            arguments = parse_tool_arguments(function.get("arguments", "{}"))
            if name == "final":
                final = str(arguments.get("final") or arguments.get("message") or "").strip()
                return ToolExecutionBatch(
                    messages=results,
                    error_signatures=error_signatures,
                    call_signatures=call_signatures,
                    final=final,
                )
            compact_arguments = compact_tool_arguments(name, arguments)
            call_signatures.append(tool_call_signature(name, arguments))
            diagnostic(f"tool: {name} {compact_arguments}")
            result = call_tool(root, name, arguments)
            content = tool_observation(name, True, result)
        except (AgentError, ToolError) as exc:
            diagnostic(f"tool error: {name} {exc}")
            error_signatures.append(f"{name}: {exc}")
            content = tool_observation(name, False, str(exc))
        results.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.get("id", name),
                "content": content,
            }
        )
    return ToolExecutionBatch(messages=results, error_signatures=error_signatures, call_signatures=call_signatures)


def parse_text_protocol(content: str) -> dict[str, Any] | None:
    """Parse a JSON text protocol message from content, returning None if invalid."""
    stripped = content.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def execute_text_protocol(root: Path, parsed: dict[str, Any]) -> ToolExecutionBatch | None:
    """Execute a tool call from a text-protocol JSON message."""
    if "final" in parsed:
        return None
    name = str(parsed.get("tool", ""))
    if not name:
        return None
    arguments = {key: value for key, value in parsed.items() if key != "tool"}
    compact_arguments = compact_tool_arguments(name, arguments)
    diagnostic(f"text tool: {name} {compact_arguments}")
    call_signatures = [tool_call_signature(name, arguments)]
    try:
        result = call_tool(root, name, arguments)
        content = tool_observation(name, True, result)
        error_signatures = []
    except ToolError as exc:
        diagnostic(f"text tool error: {name} {exc}")
        error_signatures = [f"{name}: {exc}"]
        content = tool_observation(name, False, str(exc))
    return ToolExecutionBatch(
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        error_signatures=error_signatures,
        call_signatures=call_signatures,
    )


def repeated_error_state(
    error_signatures: list[str],
    previous_signature: str | None,
    previous_count: int,
) -> tuple[str | None, int]:
    """Track repeated error signatures, returning (signature, count) tuple."""
    if not error_signatures:
        return None, 0
    signature = "\n".join(error_signatures)
    if signature == previous_signature:
        return signature, previous_count + 1
    return signature, 1


def raise_on_repeated_tool_errors(signature: str | None, count: int, limit: int) -> None:
    """Raise AgentError if the same tool error has repeated too many times."""
    if signature and count >= limit:
        raise AgentError(f"repeated tool error {count} times: {signature}")


def raise_on_repeated_tool_calls(signature: str | None, count: int, limit: int) -> None:
    """Raise AgentError if the same tool call has repeated too many times."""
    if signature and count >= limit:
        raise AgentError(f"repeated tool call {count} times: {signature}")


def run_agent(root: Path, prompt_file: Path, settings_path: Path) -> int:
    """Run the main agent loop: prompt → LLM → tools → final response."""
    settings = read_settings(settings_path)
    task = read_task(prompt_file)
    client = OpenAICompatibleClient.from_environment(
        timeout=int(settings["request_timeout_seconds"]),
        temperature=float(settings["temperature"]),
    )
    diagnostic(f"root: {root}")
    diagnostic(f"prompt: {prompt_file}")
    diagnostic(f"model: {client.model}")
    diagnostic(f"api_base: {client.base_url}")
    diagnostic(f"step_limit: {settings['step_limit']}")

    messages = initial_messages(task)
    last_tool_error_signature: str | None = None
    repeated_tool_error_count = 0
    repeated_tool_error_limit = int(settings["repeated_tool_error_limit"])
    last_tool_call_signature: str | None = None
    repeated_tool_call_count = 0
    repeated_tool_call_limit = int(settings["repeated_tool_call_limit"])
    for step in range(1, int(settings["step_limit"]) + 1):
        diagnostic(f"step {step}: requesting model")
        message = client.complete(messages, TOOL_SCHEMAS)
        messages.append(assistant_message_for_history(message))
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            diagnostic(f"step {step}: model requested {len(tool_calls)} tool call(s)")
            execution = execute_native_tool_calls(root, message)
            if execution.final is not None:
                diagnostic(f"finished: {execution.final or '<empty final response>'}")
                return 0
            messages.extend(execution.messages)
            last_tool_error_signature, repeated_tool_error_count = repeated_error_state(
                execution.error_signatures,
                last_tool_error_signature,
                repeated_tool_error_count,
            )
            last_tool_call_signature, repeated_tool_call_count = repeated_error_state(
                execution.call_signatures,
                last_tool_call_signature,
                repeated_tool_call_count,
            )
            raise_on_repeated_tool_errors(
                last_tool_error_signature,
                repeated_tool_error_count,
                repeated_tool_error_limit,
            )
            raise_on_repeated_tool_calls(
                last_tool_call_signature,
                repeated_tool_call_count,
                repeated_tool_call_limit,
            )
            continue

        content = message.get("content") or ""
        parsed = parse_text_protocol(content)
        if parsed is not None:
            execution = execute_text_protocol(root, parsed)
            if execution is not None:
                messages.extend(execution.messages)
                last_tool_error_signature, repeated_tool_error_count = repeated_error_state(
                    execution.error_signatures,
                    last_tool_error_signature,
                    repeated_tool_error_count,
                )
                last_tool_call_signature, repeated_tool_call_count = repeated_error_state(
                    execution.call_signatures,
                    last_tool_call_signature,
                    repeated_tool_call_count,
                )
                raise_on_repeated_tool_errors(
                    last_tool_error_signature,
                    repeated_tool_error_count,
                    repeated_tool_error_limit,
                )
                raise_on_repeated_tool_calls(
                    last_tool_call_signature,
                    repeated_tool_call_count,
                    repeated_tool_call_limit,
                )
                continue
            final = str(parsed.get("final", "")).strip()
        else:
            final = content.strip()

        diagnostic(f"finished: {final or '<empty final response>'}")
        return 0

    raise AgentError(f"step limit exceeded: {settings['step_limit']}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the agent runner."""
    parser = argparse.ArgumentParser(description="Run the local ai-lives agent.")
    parser.add_argument("--root", required=True, help="Session worktree root.")
    parser.add_argument("--prompt-file", required=True, help="Prompt file generated by run_session.py.")
    parser.add_argument(
        "--settings",
        default="config/project.toml",
        help="Project settings path, relative to --root unless absolute.",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point: parse args, resolve paths, run agent or return error code."""
    args = parse_args()
    root = Path(args.root).resolve()
    prompt_file = Path(args.prompt_file)
    if not prompt_file.is_absolute():
        prompt_file = root / prompt_file
    settings_path = Path(args.settings)
    if not settings_path.is_absolute():
        settings_path = root / settings_path

    try:
        return run_agent(root, prompt_file, settings_path)
    except (AgentError, ToolError, LlmClientError) as exc:
        print(f"agent session failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())