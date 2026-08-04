#!/usr/bin/env bash
# Готовит аудиофрагмент для загрузки в Telegram:
# показывает исходные теги, убирает спойлеры, сохраняет атрибуцию.

set -eu

if [ $# -lt 1 ]; then
    echo "Использование: prepare.sh <исходный.mp3> [выходной.mp3]" >&2
    exit 1
fi

SRC="$1"
OUT="${2:-fragment.mp3}"

if [ ! -f "$SRC" ]; then
    echo "Файл не найден: $SRC" >&2
    exit 1
fi

probe() {
    ffprobe -hide_banner -i "$1" 2>&1 || true
}

echo "=== Теги исходника ==="
probe "$SRC" | sed -n '/Metadata:/,/Duration:/p'

echo
echo "=== Потоки исходника ==="
probe "$SRC" | grep 'Stream #' || true

echo
ffmpeg -y -loglevel error -i "$SRC" -vn \
    -metadata title="Фрагмент" \
    -metadata album= \
    -codec copy "$OUT"

echo "=== Теги готового файла: $OUT ==="
probe "$OUT" | sed -n '/Metadata:/,/Duration:/p'

echo
echo "Проверь: title нейтральный, artist и comment с копирайтом на месте,"
echo "полей с названием произведения не осталось."
echo "Дальше: отправь $OUT боту — он вернёт file_id."
