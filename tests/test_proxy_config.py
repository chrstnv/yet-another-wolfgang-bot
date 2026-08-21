import base64

import pytest

from tools.proxy_config import build, choose, name_of, nodes

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

def test_trojan_keeps_the_password_and_the_disguise():
    node = outbound("trojan://пароль@узел.example:443?security=tls&sni=a.example#TR")

    assert node["settings"]["servers"][0]["password"] == "пароль"
    assert node["streamSettings"]["tlsSettings"]["serverName"] == "a.example"

SUBSCRIPTION = [
    "ss://YWVzLTI1Ni1nY206cGFzcw@ss.example:8388#%F0%9F%87%BA%F0%9F%87%B8%20US%20%5BSS%5D",
    "trojan://pass@tr.example:443?security=tls#%F0%9F%87%A9%F0%9F%87%AA%20DE%20%5BTrojan%5D",
    "vless://uuid@plain.example:443?security=tls#%F0%9F%87%AC%F0%9F%87%A7%20GB%20%5BVLESS%5D",
    "vless://uuid@real.example:443?security=reality&pbk=k#%F0%9F%87%AB%F0%9F%87%AE%20FN%20%5BVLESS%5D",
    "vless://uuid@moscow.example:443?security=reality&pbk=k#%F0%9F%87%B7%F0%9F%87%BA%20RU%20%5BVLESS%5D",
]

def test_nodes_reads_a_subscription_hidden_in_base64():
    packed = base64.b64encode("\n".join(SUBSCRIPTION).encode()).decode()

    assert nodes(packed) == SUBSCRIPTION

def test_nodes_reads_a_subscription_in_the_open():
    assert nodes("\n".join(SUBSCRIPTION)) == SUBSCRIPTION

def test_name_is_read_through_the_percent_signs():
    assert name_of(SUBSCRIPTION[1]) == "🇩🇪 DE [Trojan]"

def test_the_best_disguise_wins():
    """Reality прикидывается чужим сайтом — остальные заметнее."""
    assert choose(SUBSCRIPTION) == SUBSCRIPTION[3]

def test_a_node_at_home_is_never_chosen():
    """Узел в стране сервера маршрута не меняет — выбирать его незачем."""
    assert choose([SUBSCRIPTION[4], SUBSCRIPTION[0]]) == SUBSCRIPTION[0]

def test_nothing_but_home_leaves_nothing_to_choose():
    with pytest.raises(SystemExit):
        choose([SUBSCRIPTION[4]])

def test_a_wish_narrows_the_choice():
    assert choose(SUBSCRIPTION, "GB") == SUBSCRIPTION[2]

def test_an_impossible_wish_is_said_out_loud():
    with pytest.raises(SystemExit):
        choose(SUBSCRIPTION, "Антарктида")
