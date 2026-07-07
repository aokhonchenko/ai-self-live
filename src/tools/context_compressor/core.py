"""Ядро инструмента сжатия файлов памяти сессии.

Удаляет дубликаты, старые записи сессий и пустые секции,
сохраняя актуальальное состояние.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CompressionResult:
    """Результат сжатия файла."""

    original_lines: int = 0
    compressed_lines: int = 0
    removed_lines: int = 0
    removed_duplicates: int = 0
    removed_empty: int = 0
    removed_old_sessions: int = 0
    removed_noise: int = 0
    kept_sessions: list[str] = field(default_factory=list)
    removed_sessions: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    compressed_text: str = ""

    @property
    def compression_ratio(self) -> float:
        if self.original_lines == 0:
            return 0.0
        return self.removed_lines / self.original_lines

    @property
    def size_reduction_pct(self) -> float:
        if self.original_lines == 0:
            return 0.0
        return round((1 - self.compressed_lines / self.original_lines) * 100, 1)


SESSION_HEADER_RE = re.compile(r"^## Сессия\s+(\d+)", re.MULTILINE)
SESSION_DATE_RE = re.compile(r"Дата:\s*(\d{4}-\d{2}-\d{2})")
FAILURE_BLOCK_RE = re.compile(
    r"(## Сессия была прервана\n\nСессия была прервана\. "
    r"Последние 50 строк сохранены в `[^`]+`\.\n*){2,}",
    re.MULTILINE,
)
EMPTY_LINE_RE = re.compile(r"^\s*$")
TRIPLE_DASH_RE = re.compile(r"^---\s*$")
DEEP_HEADER_RE = re.compile(r"^#{5,}\s")


def detect_duplicates(text: str, min_lines: int = 3, min_matches: int = 2) -> dict[str, Any]:
    """Найти повторяющиеся блоки строк.

    Args:
        text: Текст файла.
        min_lines: Минимальное количество строк в блоке.
        min_matches: Минимальное количество повторений.

    Returns:
        Словарь с информацией о дубликатах.
    """
    lines = text.splitlines()
    duplicates: dict[tuple[str, ...], list[int]] = {}

    for i in range(len(lines) - min_lines + 1):
        block = tuple(lines[i : i + min_lines])
        if block in duplicates:
            duplicates[block].append(i)
        else:
            duplicates[block] = [i]

    reported: set[int] = set()
    result_duplicates: list[dict[str, Any]] = []

    for block, positions in duplicates.items():
        if len(positions) < min_matches:
            continue
        block_key = str(block)
        if any(block_key in str(tuple(lines[s : s + len(block)])) for s in reported):
            continue
        reported.update(positions)
        result_duplicates.append({
            "lines": len(block),
            "occurrences": len(positions),
            "positions": positions,
            "preview": "\n".join(block[:3]),
        })

    total_wasted = sum(d["occurrences"] - 1 for d in result_duplicates) * min_lines

    return {
        "duplicate_count": len(result_duplicates),
        "duplicate_wasted_lines": total_wasted,
        "duplicates": result_duplicates,
    }


def assess_noise(text: str) -> dict[str, Any]:
    """Оценить процент шумных строк.

    Args:
        text: Текст файла.

    Returns:
        Словарь с метриками шума.
    """
    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return {"noise_lines": 0, "noise_ratio": 0.0, "types": {}}

    noise_types: dict[str, int] = {
        "empty": 0, "separator": 0, "deep_header": 0,
        "table_row": 0, "code_fence": 0,
    }

    for line in lines:
        stripped = line.strip()
        if EMPTY_LINE_RE.match(stripped):
            noise_types["empty"] += 1
        elif TRIPLE_DASH_RE.match(stripped):
            noise_types["separator"] += 1
        elif DEEP_HEADER_RE.match(stripped):
            noise_types["deep_header"] += 1
        elif stripped.startswith("|") and stripped.endswith("|"):
            noise_types["table_row"] += 1
        elif stripped == "```":
            noise_types["code_fence"] += 1

    noise_lines = sum(noise_types.values())
    return {
        "noise_lines": noise_lines,
        "noise_ratio": round(noise_lines / total * 100, 1),
        "types": noise_types,
    }


def suggest_compression(sections: list[dict[str, Any]], total_tokens: int) -> list[str]:
    """Сгенерировать рекомендации по сжатию."""
    recommendations: list[str] = []
    if total_tokens > 25000:
        recommendations.append(f"Промпт большой ({total_tokens} токенов) - рассмотрите сжатие")
    for section in sections:
        if section.get("duplicate_count", 0) > 0:
            recommendations.append(
                f"Секция '{section.get('name', '?')}': {section['duplicate_count']} дубликатов"
            )
        noise_data = section.get("noise", {})
        if isinstance(noise_data, dict) and noise_data.get("noise_ratio", 0) > 20:
            recommendations.append(
                f"Секция '{section.get('name', '?')}': {noise_data['noise_ratio']}% шума"
            )
    return recommendations


def extract_session_blocks(text: str) -> list[dict[str, Any]]:
    """Извлечь все блоки сессий из текста."""
    blocks: list[dict[str, Any]] = []
    lines = text.splitlines(keepends=True)

    session_positions: list[int] = []
    for i, line in enumerate(lines):
        if SESSION_HEADER_RE.match(line):
            session_positions.append(i)

    for idx, pos in enumerate(session_positions):
        match = SESSION_HEADER_RE.match(lines[pos])
        session_num = int(match.group(1)) if match else 0

        session_date = None
        for j in range(pos + 1, min(pos + 6, len(lines))):
            date_match = SESSION_DATE_RE.search(lines[j])
            if date_match:
                session_date = date_match.group(1)
                break

        end_pos = session_positions[idx + 1] if idx + 1 < len(session_positions) else len(lines)
        block_text = "".join(lines[pos:end_pos])

        blocks.append({
            "number": session_num,
            "date": session_date,
            "text": block_text,
            "start_line": pos + 1,
            "end_line": end_pos,
        })

    return blocks


def compress_last_session(
    text: str,
    keep_recent: int = 5,
    remove_duplicates: bool = True,
    remove_noise: bool = True,
) -> CompressionResult:
    """Сжать файл last_session.md.

    Args:
        text: Исходный текст файла.
        keep_recent: Сколько последних сессий оставить.
        remove_duplicates: Удалять ли дубликаты.
        remove_noise: Удалять ли шумные строки.

    Returns:
        Результат сжатия.
    """
    result = CompressionResult(original_lines=len(text.splitlines()))

    if remove_duplicates:
        dup_info = detect_duplicates(text)
        result.removed_duplicates = dup_info["duplicate_wasted_lines"]
        text = FAILURE_BLOCK_RE.sub(
            lambda m: m.group(0).split("\n\n")[0] + "\n\n", text
        )

    blocks = extract_session_blocks(text)

    if blocks:
        blocks.sort(key=lambda b: b["number"])
        sessions_to_keep = blocks[-keep_recent:] if len(blocks) > keep_recent else blocks
        sessions_to_remove = blocks[: len(blocks) - len(sessions_to_keep)]

        result.kept_sessions = [f"сессия {b['number']}" for b in sessions_to_keep]
        result.removed_sessions = [f"сессия {b['number']}" for b in sessions_to_remove]
        result.removed_old_sessions = sum(
            len(b["text"].splitlines()) for b in sessions_to_remove
        )

        first_session_line = blocks[0]["start_line"] - 1
        header_text = "".join(text.splitlines(keepends=True)[:first_session_line])
        last_block = blocks[-1]
        footer_start = last_block["end_line"]
        footer_text = "".join(text.splitlines(keepends=True)[footer_start:])

        new_lines = [header_text]
        for block in sessions_to_keep:
            new_lines.append(block["text"])
        new_lines.append(footer_text)
        text = "\n".join(new_lines)

    if remove_noise:
        noise_info = assess_noise(text)
        result.removed_noise = noise_info["noise_lines"]
        compressed_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if EMPTY_LINE_RE.match(stripped):
                continue
            if TRIPLE_DASH_RE.match(stripped):
                continue
            compressed_lines.append(line)
        text = "\n".join(compressed_lines)

    result.compressed_lines = len(text.splitlines())
    result.removed_lines = result.original_lines - result.compressed_lines
    result.compressed_text = text

    if result.removed_duplicates > 0:
        result.recommendations.append(f"Удалено {result.removed_duplicates} строк дубликатов")
    if result.removed_old_sessions > 0:
        result.recommendations.append(
            f"Удалено {len(sessions_to_remove) if blocks else 0} старых записей сессий"
        )
    if result.removed_noise > 0:
        result.recommendations.append(f"Удалено {result.removed_noise} шумных строк")
    if result.compression_ratio > 0.3:
        result.recommendations.append("Файл сильно разросся - рекомендуется регулярная очистка")

    return result


def format_compression_result(result: CompressionResult) -> str:
    """Сформатировать результат сжатия в читаемый текст."""
    lines: list[str] = []
    lines.append("=" * 50)
    lines.append("  Результат сжатия")
    lines.append("=" * 50)
    lines.append(f"  Строк до:    {result.original_lines}")
    lines.append(f"  Строк после: {result.compressed_lines}")
    lines.append(f"  Удалено:     {result.removed_lines} ({result.size_reduction_pct}%)")
    lines.append("")
    lines.append(f"  Дубликатов:  {result.removed_duplicates} строк")
    lines.append(f"  Старых сессий: {result.removed_old_sessions} строк")
    lines.append(f"  Шума:        {result.removed_noise} строк")
    lines.append("")

    if result.kept_sessions:
        lines.append(f"  Оставлено сессий: {', '.join(result.kept_sessions)}")
    if result.removed_sessions:
        lines.append(f"  Удалено сессий: {', '.join(result.removed_sessions)}")
    lines.append("")

    if result.recommendations:
        lines.append("  Рекомендации:")
        for rec in result.recommendations:
            lines.append(f"    - {rec}")

    lines.append("=" * 50)
    return "\n".join(lines)
