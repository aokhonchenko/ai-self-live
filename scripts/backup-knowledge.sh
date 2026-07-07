#!/bin/bash
# Скрипт резервного копирования знаний (ai-lives)
# Архивирует содержимое каталога knowledge/ в tar.gz

set -e  # Остановка при первой ошибке

KNOWLEDGE_DIR="${1:-knowledge}"
BACKUP_NAME="backup-knowledge-$(date +%Y%m%d-%H%M%S).tar.gz"
BASE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Проверка существования каталога знаний
if [ ! -d "$KNOWLEDGE_DIR" ]; then
    echo "Ошибка: Каталог '$KNOWLEDGE_DIR' не найден." >&2
    exit 1
fi

echo "Резервное копирование из $BASE_PATH/$KNOWLEDGE_DIR в $BACKUP_NAME..."

# Создание архива (исключая скрытые файлы и логи)
tar -czf "$BASE_PATH/$BACKUP_NAME" \
    --exclude='.*' \
    --exclude='.git/' \
    --exclude='logs/*' \
    "$KNOWLEDGE_DIR"

echo "Готово: $BACKUP_NAME создан."
echo "Размер архива: $(du -h "$BASE_PATH/$BACKUP_NAME" | cut -f1)"
