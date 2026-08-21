"""Делает конфиг Xray из ссылки подписки — чтобы не собирать JSON руками.

    python -m tools.proxy_config "vless://..." > proxy.json
    python -m tools.proxy_config "$(cat ссылка.txt)" > proxy.json

На выходе — прокси SOCKS5, через который бот ходит в Телеграм. Всё остальное
(реестр образов, входящий SSH для выкладки) продолжает ходить напрямую: это
и есть причина городить прокси, а не заворачивать в туннель всю машину.

Понимает vless:// и ss:// — то, что отдают провайдеры с обфускацией. Ссылка
содержит пароль, поэтому файл с ней держите с правами 600 и не коммитьте.
"""

import base64
import json
import sys
from urllib.parse import parse_qs, unquote, urlparse

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

def vless_outbound(url) -> dict:
    query = {key: value[0] for key, value in parse_qs(url.query).items()}
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
        "streamSettings": stream,
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

def build(link: str) -> dict:
    url = urlparse(link.strip())

    if url.scheme == "vless":
        outbound = vless_outbound(url)
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
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    json.dump(build(sys.argv[1]), sys.stdout, ensure_ascii=False, indent=2)
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
