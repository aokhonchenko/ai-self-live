# Запуск проекта

Проект использует `uv` и локального минимального агента без внешнего agent framework.

## Установка

```bash
uv sync
```

После синхронизации доступны тесты и скрипты проекта. Отдельные agent framework пакеты не требуются.

## Настройка модели

Скопируйте пример окружения:

```bash
cp .env.example .env
```

Заполните `.env`:

```bash
AI_API_KEY=
AI_BASE_URL=https://your-openai-compatible-endpoint.example/v1
AI_MODEL=your-model-name
```

`AI_API_KEY` можно оставить пустым, если endpoint не требует авторизации. `config/project.toml` хранит только не-секретные параметры локального агента:

```toml
[agent]
step_limit = 300
request_timeout_seconds = 300
repeated_tool_error_limit = 3
repeated_tool_call_limit = 3
temperature = 0.2
```

## Проверка без модели

Собрать активный промпт без запуска агента:

```bash
uv run python scripts/run_session.py --dry-run
```

Запустить тесты:

```bash
uv run python -m pytest
```

## Обычный запуск сессии

```bash
uv run python scripts/session_transaction.py
```

Транзакционный runner создаёт временный `git worktree` в `runs/session-NNNN`, запускает там сессию, проверяет результат тестами и применяет изменения только при полном успехе. Если успешная сессия изменила внешний проект в `projects/` с собственным `.git` или git-ignore правилом агента, runner реплицирует этот каталог отдельно от merge-коммита. Перед удалением worktree он сохраняет отладочный снимок в `runs/snapshots/`; хранятся два последних снимка.

По умолчанию он вызывает локального агента:

```bash
uv run python scripts/run_agent.py --root "{ROOT}" --prompt-file "{PROMPT_FILE}"
```

## Прямой запуск агента

Для отладки можно вызвать агента напрямую из корня проекта или временного worktree:

```bash
uv run python scripts/run_agent.py --root . --prompt-file state/active_prompt.md
```

В обычной работе предпочтителен `scripts/session_transaction.py`, потому что он обеспечивает атомарность и откат при падении.

## Что будет видно в консоли

- `[session] ...` - этапы транзакционного runner'а.
- `[cmd] ...` - внешние команды, которые запускает runner.
- `[wait] ...` - команда всё ещё работает и не пишет вывод.
- `[agent] ...` - шаги локального агента, обращения к модели и вызовы файловых инструментов.

## Инструменты агента

Локальный агент получает инструменты из реестра `scripts/file_tools.py`. Реестр при старте сканирует директории `src/tools/*/tool.py` и собирает из каждого инструмента:

- `schema()` - OpenAI-compatible function schema для tool calling;
- `passport()` - строку для runtime-паспорта агента;
- `handle(root, arguments)` - обработчик вызова.

Сейчас через этот механизм доступны файловые инструменты, а также `run_command`, `run_pytest` и `run_python_script`. Актуальный список не нужно поддерживать вручную в `SYSTEM_PROMPT.md`: он генерируется из директорий инструментов.

Если инструмент не может выполнить действие, ошибка возвращается модели как `ok:false`. Например, отсутствие файла не роняет процесс агента: модель получает наблюдение и должна выбрать следующий шаг.

### Как добавить инструмент

1. Создать директорию `src/tools/<tool_name>/`.
2. Добавить `__init__.py` и `tool.py`.
3. В `tool.py` реализовать `schema()`, `passport()` и `handle(root, arguments)`.
4. Для путей использовать `safe_path()` или `safe_cwd()` из `src.tools._runtime`.
5. Ошибки валидации отдавать через `ToolError`.
6. Добавить тесты: успешный вызов через `scripts.file_tools.call_tool()` и ошибки аргументов.
7. Запустить `uv run python -m pytest`.

Подробный контракт и минимальный пример лежат в `src/tools/README.md`.

## Падение проверок

Если проверочная команда падает, `scripts/session_transaction.py` откатывает сессию. Последние 50 строк диагностического вывода сохраняются в `state/session_failure_tail.txt`, а `state/last_session.md` получает отметку о прерывании. Временный worktree сохраняется как отладочный снимок в `runs/snapshots/session-NNNN-failed`.
