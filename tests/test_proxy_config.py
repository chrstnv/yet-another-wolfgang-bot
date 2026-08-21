import base64

from tools.proxy_config import build

VLESS = (
    "vless://11111111-2222-3333-4444-555555555555@узел.example:443"
    "?type=tcp&security=reality&pbk=ABCdef&fp=chrome"
    "&sni=www.microsoft.com&sid=0123abcd&flow=xtls-rprx-vision#Узел"
)

def outbound(link: str) -> dict:
    return build(link)["outbounds"][0]

def test_the_proxy_listens_for_the_bot():
    inbound = build(VLESS)["inbounds"][0]

    assert inbound["protocol"] == "socks"
    assert inbound["port"] == 1080

def test_vless_keeps_the_identity_and_the_address():
    node = outbound(VLESS)["settings"]["vnext"][0]

    assert node["address"] == "узел.example"
    assert node["port"] == 443
    assert node["users"][0]["id"] == "11111111-2222-3333-4444-555555555555"
    assert node["users"][0]["flow"] == "xtls-rprx-vision"

def test_reality_carries_its_keys():
    """Без publicKey и shortId узел не отзовётся, а ошибка будет невнятной."""
    reality = outbound(VLESS)["streamSettings"]["realitySettings"]

    assert reality["publicKey"] == "ABCdef"
    assert reality["shortId"] == "0123abcd"
    assert reality["serverName"] == "www.microsoft.com"

def test_shadowsocks_reads_an_open_link():
    node = outbound("ss://aes-256-gcm:пароль@узел.example:8388")["settings"]["servers"][0]

    assert node == {
        "address": "узел.example",
        "port": 8388,
        "method": "aes-256-gcm",
        "password": "пароль",
    }

def test_shadowsocks_reads_credentials_hidden_in_base64():
    secret = base64.b64encode("aes-256-gcm:пароль".encode()).decode()
    node = outbound(f"ss://{secret}@узел.example:8388#Узел")["settings"]["servers"][0]

    assert node["method"] == "aes-256-gcm"
    assert node["password"] == "пароль"

def test_shadowsocks_reads_a_link_hidden_whole():
    secret = base64.b64encode("aes-256-gcm:пароль@узел.example:8388".encode()).decode()
    node = outbound(f"ss://{secret}#Узел")["settings"]["servers"][0]

    assert node["address"] == "узел.example"
    assert node["port"] == 8388

def test_a_slash_inside_base64_does_not_break_the_link():
    """Разборщик адресов принимает «/» за начало пути, и ссылка рассыпается."""
    secret = base64.b64encode("aes-256-gcm:пар/оль".encode()).decode()
    assert "/" in secret

    node = outbound(f"ss://{secret}@узел.example:8388")["settings"]["servers"][0]

    assert node["password"] == "пар/оль"
