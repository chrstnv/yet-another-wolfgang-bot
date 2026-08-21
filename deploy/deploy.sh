#!/bin/sh
# Выкладка новой версии. Это единственное, что разрешено делать ключу, которым
# ходит GitHub Actions: в authorized_keys он записан с
#
#     command="/opt/wolfgang/deploy.sh",restrict ssh-ed25519 AAAA...
#
# Оболочку таким ключом не получить, можно только запустить этот скрипт.
# Выкладываемая версия приходит аргументом — хешем коммита; без аргумента
# перезапускается то, что записано в image.env.
set -eu

cd /opt/wolfgang

# Аргумент из SSH_ORIGINAL_COMMAND — это строка, которую прислал кто-то снаружи,
# и подставлять её в команды без проверки нельзя. Хеш коммита выглядит ровно
# так и никак иначе
tag="${SSH_ORIGINAL_COMMAND:-}"
if [ -n "$tag" ]; then
    echo "$tag" | grep -Eq '^[0-9a-f]{40}$' || {
        echo "Это не похоже на хеш коммита, выкладка отменена"
        exit 1
    }
    sed -i "s|:[0-9a-f]\{40\}$|:$tag|" image.env
fi

# image.env — обычный файл с одной строкой BOT_IMAGE=cr.yandex/<реестр>/...
# Секретов в нём нет, поэтому он отдельно от .env с токеном
set -a
. ./image.env
set +a

# Пароль от реестра на диске не хранится: машине выдан сервисный аккаунт, и
# IAM-токен для него отдаёт служба метаданных облака
token=$(curl -sf -H "Metadata-Flavor: Google" \
    "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

echo "$token" | docker login --username iam --password-stdin cr.yandex

echo "Выкладываю $BOT_IMAGE"
docker compose pull
docker compose up -d --remove-orphans

# Старые образы копятся по одному на выкладку и съедают диск за месяц.
# Сутки оставляем на быстрый откат
docker image prune --force --filter "until=24h"

docker compose ps
