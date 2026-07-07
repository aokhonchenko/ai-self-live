#!/usr/bin/env python3
"""
Модуль самоанализа (self-review) для автономного агента.

Анализирует историю сессий (logs/history.md) и последнее состояние
(state/last_session.md), выявляя:
- Повторяющиеся проблемы
- Неиспользованные возможности
- Устаревшие артефакты
- Рекомендации по улучшению процесса

Создан: сессия 36 (2026-07-06)
Цель: дать агенту обратную связь о качестве собственной работы.
"""

import re
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import datetime


# ─── Типы данных ───────────────────────────────────────────────────

@dataclass
class SessionRecord:
    """Запись о сессии из history.md."""
    number: int
    date: str
    summary: str
    raw_line: str


@dataclass
class ReviewFinding:
    """Одна находка самоанализа."""
    category: str  # 'problem', 'opportunity', 'outdated', 'recommendation'
    severity: str  # 'high', 'medium', 'low'
    title: str
    description: str
    evidence: str  # ссылка на источник (файл, строка)
    suggestion: str  # что можно сделать


@dataclass
class ReviewReport:
    """Полный отчёт самоанализа."""
    generated_at: str
    session_count: int
    findings: List[ReviewFinding] = field(default_factory=list)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)


# ─── Парсер истории ────────────────────────────────────────────────

def parse_history(path: str = "logs/history.md") -> List[SessionRecord]:
    """
    Парсит logs/history.md и возвращает список записей о сессиях.
    
    Ожидаемый формат:
    ## Сессия N — YYYY-MM-DD
    ...
    """
    records = []
    path_obj = Path(path)
    
    if not path_obj.exists():
        return records
    
    content = path_obj.read_text(encoding='utf-8')
    
    # Ищем заголовки сессий
    pattern = r'^##\s+Сессия\s+(\d+)\s*[—–-]\s*(\d{4}[-/]\d{2}[-/]\d{2})'
    
    lines = content.split('\n')
    current_record = None
    current_lines = []
    
    for line in lines:
        match = re.match(pattern, line.strip())
        if match:
            # Сохраняем предыдущую запись
            if current_record is not None:
                current_record.summary = ' '.join(current_lines).strip()
                records.append(current_record)
            
            current_record = SessionRecord(
                number=int(match.group(1)),
                date=match.group(2),
                summary='',
                raw_line=line.strip()
            )
            current_lines = []
        elif current_record is not None:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                current_lines.append(stripped)
    
    # Последняя запись
    if current_record is not None:
        current_record.summary = ' '.join(current_lines).strip()
        records.append(current_record)
    
    return records


def parse_last_session(path: str = "state/last_session.md") -> Dict[str, str]:
    """
    Парсит state/last_session.md и возвращает секции.
    """
    sections = {}
    path_obj = Path(path)
    
    if not path_obj.exists():
        return sections
    
    content = path_obj.read_text(encoding='utf-8')
    current_section = None
    current_lines = []
    
    for line in content.split('\n'):
        if line.startswith('## '):
            if current_section is not None:
                sections[current_section] = '\n'.join(current_lines).strip()
            current_section = line.strip('## #').strip()
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)
    
    if current_section is not None:
        sections[current_section] = '\n'.join(current_lines).strip()
    
    return sections


# ─── Анализаторы ───────────────────────────────────────────────────

def find_repeated_problems(records: List[SessionRecord]) -> List[ReviewFinding]:
    """
    Ищет повторяющиеся проблемы в истории сессий.
    """
    findings = []
    
    # Собираем ключевые слова из summary
    all_text = ' '.join(r.summary for r in records).lower()
    
    # Проверяем частоту упоминаний проблем
    problem_patterns = [
        ('упал', 'падение тестов', 'medium'),
        ('баг', 'баги/ошибки', 'medium'),
        ('не найден', 'отсутствующие файлы', 'low'),
        ('дублирование', 'дублирование кода', 'medium'),
        ('устаревш', 'устаревшие артефакты', 'low'),
        ('перезапись', 'полная перезапись файлов', 'medium'),
    ]
    
    for keyword, problem, severity in problem_patterns:
        count = all_text.count(keyword)
        if count >= 3:
            findings.append(ReviewFinding(
                category='problem',
                severity=severity,
                title=f"Повторяющаяся проблема: {problem}",
                description=f"Ключевое слово '{keyword}' встречается {count} раз в истории сессий.",
                evidence="logs/history.md",
                suggestion=f"Создать автоматическую проверку или инструмент для предотвращения '{problem}'."
            ))
    
    return findings


def find_unused_opportunities(records: List[SessionRecord],
                               last_session: Dict[str, str]) -> List[ReviewFinding]:
    """
    Ищет упомянутые, но не реализованные возможности.
    """
    findings = []
    
    # Ключевые фразы, указывающие на планы
    plan_indicators = [
        'следующий шаг', 'план', 'нужно сделать',
        'рекомендация', 'создать', 'интегрировать',
        'подключить', 'добавить'
    ]
    
    # Собираем все тексты
    all_text = ' '.join(r.summary for r in records)
    for section_text in last_session.values():
        all_text += ' ' + section_text
    
    all_text_lower = all_text.lower()
    
    # Проверяем наличие ключевых фраз
    for indicator in plan_indicators:
        if indicator in all_text_lower:
            # Найдём контекст вокруг индикатора
            lines = all_text.split('\n')
            for line in lines:
                if indicator in line.lower():
                    findings.append(ReviewFinding(
                        category='opportunity',
                        severity='medium',
                        title=f"Неиспользованная возможность: {indicator}",
                        description=f"Упоминание '{indicator}' в тексте: {line.strip()[:100]}",
                        evidence="state/last_session.md или logs/history.md",
                        suggestion="Проверить, реализовано ли это. Если нет — добавить в план."
                    ))
                    break  # одно нахождение на индикатор
    
    return findings


def find_outdated_artifacts(records: List[SessionRecord]) -> List[ReviewFinding]:
    """
    Ищет признаки устаревших артефактов.
    """
    findings = []
    
    # Проверяем, есть ли сессии, которые только обновляли файлы без нового контента
    update_only_count = 0
    for r in records:
        summary_lower = r.summary.lower()
        if ('обновлён' in summary_lower or 'обновлен' in summary_lower) and \
           ('создан' not in summary_lower and 'созда' not in summary_lower):
            update_only_count += 1
    
    if update_only_count >= 3:
        findings.append(ReviewFinding(
            category='outdated',
            severity='low',
            title="Много сессий только с обновлениями",
            description=f"{update_only_count} сессий содержат только обновления без создания нового.",
            evidence="logs/history.md",
            suggestion="Проверить, не застрял ли агент в цикле обслуживания вместо создания ценности."
        ))
    
    return findings


def analyze_session_gaps(records: List[SessionRecord]) -> List[ReviewFinding]:
    """
    Анализирует пробелы в последовательности сессий.
    """
    findings = []
    
    if not records:
        return findings
    
    numbers = sorted([r.number for r in records])
    
    # Проверяем пропуски в нумерации
    expected = list(range(numbers[0], numbers[-1] + 1))
    missing = set(expected) - set(numbers)
    
    if missing:
        findings.append(ReviewFinding(
            category='problem',
            severity='low',
            title=f"Пропуски в нумерации сессий",
            description=f"Отсутствуют записи о сессиях: {sorted(missing)}",
            evidence="logs/history.md",
            suggestion="Проверить, не потеряны ли файлы сессий."
        ))
    
    # Проверяем давность последней сессии
    if records:
        last = records[-1]
        try:
            last_date = datetime.strptime(last.date, '%Y-%m-%d')
            now = datetime.now()
            days_since = (now - last_date).days
            if days_since > 7:
                findings.append(ReviewFinding(
                    category='recommendation',
                    severity='medium',
                    title="Давно не было сессий",
                    description=f"Последняя сессия была {days_since} дней назад ({last.date}).",
                    evidence="logs/history.md",
                    suggestion="Возможно, проект требует внимания."
                ))
        except ValueError:
            pass
    
    return findings


def generate_recommendations(records: List[SessionRecord],
                              findings: List[ReviewFinding]) -> List[str]:
    """
    Генерирует рекомендации на основе всех находок.
    """
    recs = []
    
    # Группируем по категориям
    high_priority = [f for f in findings if f.severity == 'high']
    medium_priority = [f for f in findings if f.severity == 'medium']
    
    if high_priority:
        recs.append(f"🔴 Высокий приоритет: {len(high_priority)} проблем требуют внимания.")
        for f in high_priority:
            recs.append(f"  - {f.title}: {f.suggestion}")
    
    if medium_priority:
        recs.append(f"🟡 Средний приоритет: {len(medium_priority)} возможностей для улучшения.")
        for f in medium_priority[:3]:  # топ-3
            recs.append(f"  - {f.title}: {f.suggestion}")
    
    # Анализ темпа
    if len(records) >= 5:
        recent = records[-5:]
        created_count = sum(1 for r in recent if 'создан' in r.summary.lower() or 'созда' in r.summary.lower())
        if created_count == 0:
            recs.append("📝 В последних 5 сессиях нет новых созданий — возможно, пора создать что-то новое.")
        elif created_count >= 3:
            recs.append("🚀 Хороший темп создания новых артефактов!")
    
    if not recs:
        recs.append("✅ Всё в порядке. Продолжайте текущий курс.")
    
    return recs


# ─── Главная функция ──────────────────────────────────────────────

def run_self_review(history_path: str = "logs/history.md",
                    last_session_path: str = "state/last_session.md") -> ReviewReport:
    """
    Запускает полный самоанализ и возвращает отчёт.
    
    Args:
        history_path: путь к logs/history.md
        last_session_path: путь к state/last_session.md
    
    Returns:
        ReviewReport с находками и рекомендациями
    """
    records = parse_history(history_path)
    last_session = parse_last_session(last_session_path)
    
    findings = []
    
    # Запускаем все анализаторы
    findings.extend(find_repeated_problems(records))
    findings.extend(find_unused_opportunities(records, last_session))
    findings.extend(find_outdated_artifacts(records))
    findings.extend(analyze_session_gaps(records))
    
    # Генерируем рекомендации
    recommendations = generate_recommendations(records, findings)
    
    # Сводка
    problem_count = len([f for f in findings if f.category == 'problem'])
    opportunity_count = len([f for f in findings if f.category == 'opportunity'])
    
    summary_parts = [
        f"Проанализировано {len(records)} сессий.",
    ]
    if problem_count:
        summary_parts.append(f"Найдено {problem_count} проблем.")
    if opportunity_count:
        summary_parts.append(f"Обнаружено {opportunity_count} неиспользованных возможностей.")
    if not findings:
        summary_parts.append("Критических проблем не обнаружено.")
    
    report = ReviewReport(
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        session_count=len(records),
        findings=findings,
        summary=' '.join(summary_parts),
        recommendations=recommendations
    )
    
    return report


def format_report(report: ReviewReport) -> str:
    """
    Форматирует отчёт в читаемый markdown.
    """
    lines = []
    lines.append("# Отчёт самоанализа (self-review)")
    lines.append(f"**Сгенерирован:** {report.generated_at}")
    lines.append(f"**Проанализировано сессий:** {report.session_count}")
    lines.append("")
    lines.append("## Сводка")
    lines.append("")
    lines.append(report.summary)
    lines.append("")
    
    if report.findings:
        lines.append("## Находки")
        lines.append("")
        
        # Группируем по серьёзности
        for severity in ['high', 'medium', 'low']:
            severity_findings = [f for f in report.findings if f.severity == severity]
            if not severity_findings:
                continue
            
            severity_label = {'high': '🔴 Высокий', 'medium': '🟡 Средний', 'low': '🟢 Низкий'}
            lines.append(f"### {severity_label[severity]} приоритет")
            lines.append("")
            
            for f in severity_findings:
                category_label = {
                    'problem': 'Проблема',
                    'opportunity': 'Возможность',
                    'outdated': 'Устарело',
                    'recommendation': 'Рекомендация'
                }
                lines.append(f"- **[{category_label.get(f.category, f.category)}] {f.title}**")
                lines.append(f"  - {f.description}")
                lines.append(f"  - *Источник:* {f.evidence}")
                lines.append(f"  - *Предложение:* {f.suggestion}")
                lines.append("")
    
    if report.recommendations:
        lines.append("## Рекомендации")
        lines.append("")
        for rec in report.recommendations:
            lines.append(f"- {rec}")
        lines.append("")
    
    lines.append("---")
    lines.append(f"*Отчёт создан модулем self_review.py (сессия 36)*")
    
    return '\n'.join(lines)


# ─── CLI ───────────────────────────────────────────────────────────

def main():
    """Точка входа для запуска из командной строки."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Модуль самоанализа агента"
    )
    parser.add_argument(
        '--history', default='logs/history.md',
        help='Путь к файлу истории сессий'
    )
    parser.add_argument(
        '--last-session', default='state/last_session.md',
        help='Путь к файлу последней сессии'
    )
    parser.add_argument(
        '--output', '-o', default=None,
        help='Сохранить отчёт в файл (по умолчанию — stdout)'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Вывести в JSON (по умолчанию — markdown)'
    )
    
    args = parser.parse_args()
    
    report = run_self_review(args.history, args.last_session)
    
    if args.json:
        import json
        output = json.dumps({
            'generated_at': report.generated_at,
            'session_count': report.session_count,
            'summary': report.summary,
            'findings': [
                {
                    'category': f.category,
                    'severity': f.severity,
                    'title': f.title,
                    'description': f.description,
                    'evidence': f.evidence,
                    'suggestion': f.suggestion
                }
                for f in report.findings
            ],
            'recommendations': report.recommendations
        }, ensure_ascii=False, indent=2)
    else:
        output = format_report(report)
    
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"Отчёт сохранён: {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
