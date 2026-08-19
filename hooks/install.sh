#!/bin/sh
# Ставит хуки в оба репозитория: git их не версионирует, поэтому они лежат
# здесь, а этот скрипт раскладывает их по местам.
#
#     sh hooks/install.sh
set -e

root="$(git rev-parse --show-toplevel)"
content="$(dirname "$root")/yet-another-wolfgang-content"

install -m 755 "$root/hooks/bot-pre-commit" "$root/.git/hooks/pre-commit"
echo "бот:     .git/hooks/pre-commit"

if [ -d "$content/.git" ]; then
    install -m 755 "$root/hooks/content-pre-commit" "$content/.git/hooks/pre-commit"
    echo "контент: $content/.git/hooks/pre-commit"
else
    echo "контент: репозиторий не найден, пропущено"
fi
