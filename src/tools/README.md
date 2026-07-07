# Инструменты локального агента

Каждый инструмент живёт в отдельной директории:

```text
src/tools/<tool_name>/
├── __init__.py
└── tool.py
```

`tool.py` обязан экспортировать три callable-функции:

```python
def schema() -> dict[str, Any]: ...
def passport() -> str: ...
def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]: ...
```

## Контракт

- `schema()` возвращает OpenAI-compatible function tool schema. Значение `schema()["function"]["name"]` является именем инструмента и должно быть уникальным.
- `passport()` возвращает одну или несколько строк на русском языке для runtime-паспорта агента: что делает инструмент и какие аргументы важны.
- `handle(root, arguments)` выполняет действие внутри корня сессии и возвращает JSON-совместимый словарь.
- При ошибке входных данных или нарушении границ нужно выбрасывать `ToolError` из `src.tools._runtime`, а не завершать процесс.
- Для файловых путей используй `safe_path(root, path)`, для рабочих директорий команд - `safe_cwd(root, cwd)`. Это не даёт инструменту выйти за пределы временного worktree.
- Не добавляй разрушительные действия без отдельного явного решения человека и тестов.

## Как инструмент попадает агенту

`scripts/file_tools.py` при старте сканирует `src/tools/*/tool.py`, импортирует каждый модуль и собирает:

- `TOOL_SCHEMAS` для OpenAI tool calling;
- `TOOL_PASSPORT` для runtime system prompt;
- dispatch по имени инструмента через `call_tool()`.

Поэтому после добавления новой директории не нужно править `scripts/run_agent.py` или `SYSTEM_PROMPT.md`. Достаточно реализовать `tool.py`, добавить тесты и запустить проверки.

## Минимальный пример

```python
from pathlib import Path
from typing import Any

from src.tools._runtime import ToolError


def schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "example_tool",
            "description": "Return a short example message.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    }


def passport() -> str:
    return "- `example_tool(name)` - вернуть демонстрационное сообщение."


def handle(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name", "")).strip()
    if not name:
        raise ToolError("name must be non-empty")
    return {"message": f"Привет, {name}"}
```

## Проверки

После добавления или изменения инструмента запусти:

```bash
uv run python -m pytest
```

Новый код должен быть покрыт тестами. Для инструментов обязательно проверять успешный вызов через `scripts.file_tools.call_tool()` и ошибки валидации аргументов.
