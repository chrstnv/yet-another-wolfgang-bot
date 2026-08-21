#!/bin/sh
# Перечитывает подписку и обновляет узел, через который бот ходит в Телеграм.
#
# Провайдеры меняют адреса узлов и выводят старые из строя — вшитый однажды
# адрес рано или поздно замолкает. Раз в сутки берём из подписки лучший узел
# заново; если он тот же, ничего не трогаем.
#
# Рядом должны лежать: subscription — ссылка на подписку (права 600, это тоже
# секрет), и proxy_config.py — конвертер из репозитория бота.
set -eu

cd /opt/wolfgang

SUBSCRIPTION=$(cat subscription)
PICK="${PROXY_PICK:-}"
AGENT="v2rayNG/1.8.5"

proxy_address() {
    docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
        wolfgang-proxy | head -1 | sed 's/$/:1080/'
}

# Сайт провайдера может быть закрыт с этой машины ровно так же, как Телеграм.
# Тогда идём за подпиской через уже работающий прокси — скачивает curl, а не
# питон: SOCKS питон из коробки не умеет
fetch() {
    if curl -sf -m 30 -A "$AGENT" "$SUBSCRIPTION"; then
        return 0
    fi

    echo "Напрямую подписка недоступна, иду через прокси" >&2
    curl -sf -m 30 -A "$AGENT" --socks5-hostname "$(proxy_address)" "$SUBSCRIPTION"
}

fetch | python3 proxy_config.py - ${PICK:+--pick "$PICK"} > proxy.json.new

# Пустой файл получится, если подписка не скачалась или отдала мусор. Молча
# подменить им рабочий конфиг — значит выключить бота своими руками
if [ ! -s proxy.json.new ]; then
    echo "Пустой конфиг — оставляю прежний"
    rm -f proxy.json.new
    exit 1
fi

if cmp -s proxy.json proxy.json.new; then
    rm proxy.json.new
    echo "Узел не менялся"
    exit 0
fi

mv proxy.json.new proxy.json
# владелец — nobody из контейнера с Xray: смонтированный файл сохраняет права
# хозяйской системы, и root-овый конфиг контейнер не прочитает
chown 65534:65534 proxy.json
chmod 600 proxy.json

echo "Узел сменился, перезапускаю прокси"
docker restart wolfgang-proxy
