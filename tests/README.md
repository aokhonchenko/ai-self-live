# Тесты проекта ai-lives

**Создан:** сессия 29 (2026-07-06)

## Запуск

```bash
# Через pytest (если установлен)
python -m pytest tests/ -v

# Без pytest (fallback)
python tests/test_code_analyzer.py
```

## Структура

| Файл | Что тестирует |
|------|---------------|
| `test_code_analyzer.py` | `src/tools/code_analyzer.py` — dataclass-ы, анализ файлов, директорий, форматирование отчётов, JSON, экстракторы AST, интеграционный тест (самоанализ) |

## Статистика

- Тестов: ~30
- Классов тестов: 7
- Покрывает: `analyze_file`, `analyze_directory`, `format_report`, `format_json`, `_extract_func_info`, `_extract_class_info`
