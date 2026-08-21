"""Делает конфиг Xray из ссылки на узел или из подписки провайдера.

    python -m tools.proxy_config "vless://..." > proxy.json
    python -m tools.proxy_config https://провайдер/подписка > proxy.json
    python -m tools.proxy_config https://провайдер/подписка --pick DE > proxy.json
    python -m tools.proxy_config https://провайдер/подписка --list
    curl -s https://провайдер/подписка | python -m tools.proxy_config -

На выходе — прокси SOCKS5, через который бот ходит в Телеграм. Всё остальное
(реестр образов, входящий SSH для выкладки) продолжает ходить напрямую: это
и есть причина городить прокси, а не заворачивать в туннель всю машину.

Подписка лучше отдельной ссылки: провайдеры меняют адреса узлов, и вшитый
адрес однажды перестаёт отвечать. Из подписки узел выбирается заново каждый
раз, поэтому её можно перечитывать по расписанию.

Понимает vless://, trojan:// и ss://. И ссылка, и подписка содержат пароль:
держите их с правами 600 и не коммитьте.
"""

import base64
import json
import sys
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

# на чём слушать. Внутри compose прокси — отдельная служба, и бот приходит
# к ней по сети контейнеров, наружу машины порт не выставляется
PORT = 1080

def decode_padded(raw: str) -> str:
    """base64 из ссылок приходит без выравнивания, а библиотека его требует.

    Кодировка встречается и обычная, и «безопасная для URL», поэтому символы
    второй приводим к первой.
    """
    raw = raw.replace("-", "+").replace("_", "/")

    return base64.b64decode(raw + "=" * (-len(raw) % 4)).decode()

def stream_settings(url, query: dict) -> dict:
    security = query.get("security", "none")
    stream = {"network": query.get("type", "tcp"), "security": security}

    if security == "reality":
        stream["realitySettings"] = {
            "serverName": query.get("sni", ""),
            "fingerprint": query.get("fp", "chrome"),
            "publicKey": query.get("pbk", ""),
            "shortId": query.get("sid", ""),
            "spiderX": query.get("spx", "/"),
        }
    elif security == "tls":
        stream["tlsSettings"] = {
            "serverName": query.get("sni", url.hostname),
            "fingerprint": query.get("fp", "chrome"),
        }

    if stream["network"] == "ws":
        stream["wsSettings"] = {
            "path": unquote(query.get("path", "/")),
            "headers": {"Host": query.get("host", url.hostname)},
        }
    elif stream["network"] == "grpc":
        stream["grpcSettings"] = {"serviceName": query.get("serviceName", "")}

    return stream

def vless_outbound(url) -> dict:
    query = {key: value[0] for key, value in parse_qs(url.query).items()}

    user = {"id": url.username, "encryption": query.get("encryption", "none")}
    if query.get("flow"):
        user["flow"] = query["flow"]

    return {
        "tag": "наружу",
        "protocol": "vless",
        "settings": {"vnext": [{
            "address": url.hostname,
            "port": url.port or 443,
            "users": [user],
        }]},
        "streamSettings": stream_settings(url, query),
    }

def trojan_outbound(url) -> dict:
    """Trojan прикидывается обычным сайтом за TLS — пароль и есть всё опознание."""
    query = {key: value[0] for key, value in parse_qs(url.query).items()}
    query.setdefault("security", "tls")

    return {
        "tag": "наружу",
        "protocol": "trojan",
        "settings": {"servers": [{
            "address": url.hostname,
            "port": url.port or 443,
            "password": unquote(url.username or ""),
        }]},
        "streamSettings": stream_settings(url, query),
    }

def shadowsocks_outbound(link: str) -> dict:
    """Ссылка бывает двух видов: с открытым логином и целиком в base64.

    Разбирается вручную, а не urlparse: в base64 попадается «/», и разборщик
    адресов принимает его за начало пути — ссылка рассыпается на ровном месте.
    """
    body = link[len("ss://"):].split("#")[0]

    if "@" in body:
        credentials, address = body.rsplit("@", 1)
        if ":" not in credentials or not credentials.split(":", 1)[0].islower():
            credentials = decode_padded(credentials)
    else:
        credentials, address = decode_padded(body).rsplit("@", 1)

    method, password = credentials.split(":", 1)
    host, port = address.rsplit(":", 1)

    return {
        "tag": "наружу",
        "protocol": "shadowsocks",
        "settings": {"servers": [{
            "address": host,
            "port": int(port),
            "method": method,
            "password": password,
        }]},
    }

# Узел в той же стране, где стоит сервер, ничего не меняет: маршрут остаётся
# прежним. Такие отсеиваются всегда, а не по вкусу
SAME_SIDE = ("RU", "РФ")

# чем меньше узел выделяется в потоке, тем выше место в очереди: Reality
# выглядит как обычный сайт, trojan — как обычный TLS, shadowsocks заметнее
def rank(link: str) -> int:
    if link.startswith("vless://") and "security=reality" in link:
        return 0
    if link.startswith("vless://"):
        return 1
    if link.startswith("trojan://"):
        return 2

    return 3

def name_of(link: str) -> str:
    """Название узла из ссылки — провайдеры пишут его в кодировке процентов."""
    return unquote(link.split("#", 1)[1]) if "#" in link else "без названия"

def fetch(url: str) -> str:
    # многие провайдеры отдают разное в зависимости от того, кто спрашивает:
    # клиентам v2ray — список ссылок, браузеру — страницу личного кабинета
    request = Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
    with urlopen(request, timeout=30) as answer:
        return answer.read().decode()

def nodes(body: str) -> list[str]:
    """Список ссылок из подписки. Она бывает и открытым текстом, и в base64."""
    body = body.strip()
    try:
        body = decode_padded(body)
    except Exception:
        pass

    return [line.strip() for line in body.splitlines() if "://" in line]

def choose(links: list[str], pick: str = "") -> str:
    """Лучший узел из подписки — с оглядкой на пожелание и на здравый смысл."""
    suitable = [
        link for link in links
        if not any(mark in name_of(link).upper().split() for mark in SAME_SIDE)
    ]

    if pick:
        wanted = [link for link in suitable if pick.upper() in name_of(link).upper()]
        if not wanted:
            raise SystemExit(f"Узлов с «{pick}» в подписке нет")
        suitable = wanted

    if not suitable:
        raise SystemExit("В подписке нет ни одного пригодного узла")

    return sorted(suitable, key=rank)[0]

def build(link: str) -> dict:
    url = urlparse(link.strip())

    if url.scheme == "vless":
        outbound = vless_outbound(url)
    elif url.scheme == "trojan":
        outbound = trojan_outbound(url)
    elif url.scheme == "ss":
        outbound = shadowsocks_outbound(link.strip())
    else:
        raise SystemExit(f"Не умею такие ссылки: {url.scheme or link[:20]}")

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "внутрь",
            "listen": "0.0.0.0",
            "port": PORT,
            "protocol": "socks",
            # имена бот разрешает через прокси, а не сам: локальный DNS может
            # отвечать про Телеграм что угодно
            "settings": {"udp": False, "auth": "noauth"},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
        }],
        "outbounds": [outbound],
    }

def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        print(__doc__)
        return 1

    source = arguments[0]
    pick = arguments[arguments.index("--pick") + 1] if "--pick" in arguments else ""

    # «-» значит, что подписку уже скачали и подают на вход. Так делает
    # proxy-refresh.sh: curl умеет ходить через SOCKS, а urllib — нет,
    # и на машине, где закрыт и сайт провайдера, это единственный путь
    if source == "-" or source.startswith(("http://", "https://")):
        links = nodes(sys.stdin.read() if source == "-" else fetch(source))
        if "--list" in arguments:
            for link in sorted(links, key=rank):
                print(f"{link.split('://')[0]:8} {name_of(link)}")
            return 0
        link = choose(links, pick)
        # выбранный узел печатается в поток ошибок, чтобы не попасть в конфиг,
        # но всё же попасться на глаза: молчаливый выбор потом не объяснить
        print(f"Узел: {name_of(link)}", file=sys.stderr)
    else:
        link = source

    json.dump(build(link), sys.stdout, ensure_ascii=False, indent=2)
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
