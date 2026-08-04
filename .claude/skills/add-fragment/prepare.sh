#!/usr/bin/env bash
# Готовит аудиофрагмент для загрузки в Telegram:
# показывает исходные теги, вырезает нужный кусок,
# убирает спойлеры, сохраняет атрибуцию.
#
# Использование:
#   prepare.sh <исходный> <папка-назначения> [начало] [длительность]
# Пример:
#   prepare.sh "Bach - Badinerie.mp3" prepared/bach-badinerie 0 35
#
# Файл всегда называется fragment.mp3, различаются только папки:
# Telegram показывает имя загруженного файла, и у всех карточек
# оно должно выглядеть одинаково.

set -eu

if [ $# -lt 2 ]; then
    echo "Использование: prepare.sh <исходный> <папка-назначения> [начало] [длительность]" >&2
    exit 1
fi

SRC="$1"
OUT_DIR="$2"
START="${3:-0}"
DURATION="${4:-}"

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/fragment.mp3"

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
if [ -n "$DURATION" ]; then
    ffmpeg -y -loglevel error -ss "$START" -t "$DURATION" -i "$SRC" -vn \
        -map_chapters -1 \
        -metadata title="Фрагмент" \
        -metadata album= \
        -codec copy "$OUT"
else
    ffmpeg -y -loglevel error -ss "$START" -i "$SRC" -vn \
        -map_chapters -1 \
        -metadata title="Фрагмент" \
        -metadata album= \
        -codec copy "$OUT"
fi

echo "=== Теги готового файла: $OUT ==="
probe "$OUT" | sed -n '/Metadata:/,/Stream #0:1/p'

echo
echo "Проверь: title нейтральный, artist и comment с копирайтом на месте,"
echo "полей с названием произведения не осталось."
echo "Дальше: отправь $OUT боту — он вернёт file_id."
