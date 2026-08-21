#!/bin/sh
# Суточная выгрузка базы в Object Storage. Ставится systemd-таймером, см.
# docs/deploy.md.
#
# Копировать работающую базу обычным cp нельзя: SQLite пишет страницами, и в
# копию попадёт середина транзакции. Штатный способ — .backup, он снимает
# согласованный снимок под блокировкой.
set -eu

BUCKET="${BACKUP_BUCKET:?не задан BACKUP_BUCKET}"
DATA=/opt/wolfgang/data
STAMP=$(date -u +%Y-%m-%dT%H-%M)
WORK=$(mktemp -d)

trap 'rm -rf "$WORK"' EXIT

sqlite3 "$DATA/bot.db" ".backup '$WORK/bot.db'"

# Незавершённые квизы: файл маленький, а без него после восстановления у людей
# останутся кнопки от сессий, которых нет
cp "$DATA/state.pickle" "$WORK/state.pickle" 2>/dev/null || true

tar -czf "$WORK/$STAMP.tar.gz" -C "$WORK" bot.db state.pickle 2>/dev/null \
    || tar -czf "$WORK/$STAMP.tar.gz" -C "$WORK" bot.db

# yc берёт права у сервисного аккаунта машины — статических ключей на диске нет
yc storage s3 cp "$WORK/$STAMP.tar.gz" "s3://$BUCKET/db/$STAMP.tar.gz"

echo "Выгружено: $STAMP.tar.gz"
