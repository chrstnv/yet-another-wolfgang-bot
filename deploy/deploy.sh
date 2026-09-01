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

# compose.yaml лежит на машине отдельной копией: он принадлежит root, и
# выкладке его переписывать нельзя — иначе коммитом в репозиторий можно было бы
# смонтировать в контейнер что угодно. Но разойтись эти две копии могут молча,
# и заметить это потом почти невозможно: правка драйвера логов однажды не
# доехала, а искали её полчаса посреди расследования. Поэтому сверяем и говорим
if docker run --rm --entrypoint cat "$BOT_IMAGE" /app/compose.yaml > /tmp/compose.image 2>/dev/null; then
    if ! cmp -s /tmp/compose.image compose.yaml; then
        echo
        echo "ВНИМАНИЕ: compose.yaml на машине разошёлся с репозиторием"
        diff -u compose.yaml /tmp/compose.image || true
        echo "Выкладка идёт со старым файлом — новый нужно положить руками"
        echo
    fi
    rm -f /tmp/compose.image
else
    echo "В образе нет compose.yaml — сверить описание запуска не с чем"
fi

docker compose up -d --remove-orphans

# Старые образы копятся по одному на выкладку и съедают диск за месяц.
# Сутки оставляем на быстрый откат
docker image prune --force --filter "until=24h"

docker compose ps
