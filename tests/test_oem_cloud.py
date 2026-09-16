from proscenic_830p.adapter import find_host_for_gw_id
from proscenic_830p.constants import KNOWN_DEVICE_ID, KNOWN_MAC, KNOWN_UUID
from proscenic_830p.oem_cloud import (
    InvalidAuthentication,
    ProscenicOemApi,
    discover_830p,
    map_cloud_device,
    sign_request,
)


def test_known_830p_identity() -> None:
    assert KNOWN_DEVICE_ID == "bf4d77d05964608b34enbm"
    assert KNOWN_UUID == "936b5c32ba35da61"
    assert KNOWN_MAC == "68:57:2d:87:87:e9"


def test_sign_request_is_stable() -> None:
    sig = sign_request("secret", {"a": "x", "clientId": "abc", "time": "1"})
    again = sign_request("secret", {"time": "1", "a": "x", "clientId": "abc"})
    assert sig == again
    assert len(sig) == 64


def test_map_cloud_device() -> None:
    device = map_cloud_device(
        {
            "name": "830P",
            "devId": KNOWN_DEVICE_ID,
            "localKey": "0123456789abcdef",
            "uuid": KNOWN_UUID,
            "productId": "ofqlgafdltzahwlh",
            "category": "sd",
            "dps": {"39": 80},
        }
    )
    assert device.device_id == KNOWN_DEVICE_ID
    assert device.local_key == "0123456789abcdef"
    assert device.dps["39"] == 80


def test_oem_login_and_find_830p() -> None:
    calls: list[str] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        calls.append(action)
        if action == "tuya.m.user.email.token.create":
            return {
                "success": True,
                "result": {"publicKey": "65537", "exponent": "65537", "token": "tok"},
            }
        if action == "tuya.m.user.email.password.login":
            return {"success": True, "result": {"sid": "sid-1"}}
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {
                "success": True,
                "result": [
                    {
                        "name": "Saugroboter",
                        "devId": KNOWN_DEVICE_ID,
                        "localKey": "abcdef0123456789",
                        "uuid": KNOWN_UUID,
                        "productId": "ofqlgafdltzahwlh",
                        "category": "sd",
                        "dps": {"38": 5},
                    }
                ],
            }
        raise AssertionError(action)

    api = ProscenicOemApi("user@example.com", "pw", region="eu", http_post=http_post)
    api.login()
    found = api.find_830p(device_id=KNOWN_DEVICE_ID)
    assert found is not None
    assert found.local_key == "abcdef0123456789"
    assert "tuya.m.user.email.password.login" in calls


def test_oem_wrong_password() -> None:
    def http_post(url, params=None, data=None):
        if params["a"] == "tuya.m.user.email.token.create":
            return {
                "success": True,
                "result": {"publicKey": "65537", "exponent": "65537", "token": "tok"},
            }
        return {
            "success": False,
            "errorCode": "USER_PASSWD_WRONG",
            "errorMsg": "wrong",
        }

    api = ProscenicOemApi("user@example.com", "bad", http_post=http_post)
    try:
        api.login()
    except InvalidAuthentication:
        return
    raise AssertionError("expected InvalidAuthentication")


def test_discover_830p_returns_lan_config_without_password() -> None:
    def http_post(url, params=None, data=None):
        action = params["a"]
        if action == "tuya.m.user.email.token.create":
            return {
                "success": True,
                "result": {"publicKey": "65537", "exponent": "65537", "token": "tok"},
            }
        if action == "tuya.m.user.email.password.login":
            return {"success": True, "result": {"sid": "sid-1"}}
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {
                "success": True,
                "result": [
                    {
                        "name": "Saugroboter",
                        "devId": KNOWN_DEVICE_ID,
                        "localKey": "abcdef0123456789",
                        "uuid": KNOWN_UUID,
                        "productId": "ofqlgafdltzahwlh",
                        "category": "sd",
                        "dps": {},
                    }
                ],
            }
        raise AssertionError(action)

    cfg = discover_830p(
        "user@example.com",
        "pw",
        http_post=http_post,
        hosts_by_gwid={KNOWN_DEVICE_ID: "192.168.178.63"},
    )
    assert cfg["host"] == "192.168.178.63"
    assert cfg["device_id"] == KNOWN_DEVICE_ID
    assert cfg["local_key"] == "abcdef0123456789"
    assert "password" not in cfg


def _oem_http(devices: list[dict]) -> callable:
    def http_post(url, params=None, data=None):
        action = params["a"]
        if action == "tuya.m.user.email.token.create":
            return {
                "success": True,
                "result": {"publicKey": "65537", "exponent": "65537", "token": "tok"},
            }
        if action == "tuya.m.user.email.password.login":
            return {"success": True, "result": {"sid": "sid-1"}}
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {"success": True, "result": devices}
        raise AssertionError(action)

    return http_post


SCHLURP_D600 = {
    "name": "schlurp",
    "devId": "bfschlurp830pxxxxxx",
    "localKey": "schlurplocalkey99",
    "uuid": "cccccccccccccccc",
    "productId": "d600pidxxxxxxxx",
    "productName": "D600",
    "category": "sd",
}

PLUG = {
    "name": "Steckdose",
    "devId": "bfplugxxxxxxxxxxxx",
    "localKey": "pluglocalkeyplug1",
    "uuid": "dddddddddddddddd",
    "productId": "plugpid",
    "category": "cz",
}


def test_discover_accepts_schlurp_listed_as_d600() -> None:
    cfg = discover_830p(
        "user@example.com",
        "pw",
        http_post=_oem_http([SCHLURP_D600]),
    )
    assert cfg["local_key"] == "schlurplocalkey99"
    assert cfg["device_id"] == "bfschlurp830pxxxxxx"
    assert cfg["name"] == "schlurp"


def test_discover_picks_schlurp_among_non_vacuum() -> None:
    cfg = discover_830p(
        "user@example.com",
        "pw",
        http_post=_oem_http([PLUG, SCHLURP_D600]),
    )
    assert cfg["local_key"] == "schlurplocalkey99"
    assert cfg["device_id"] == "bfschlurp830pxxxxxx"


def test_discover_prefers_known_id_over_other_names() -> None:
    other = dict(SCHLURP_D600)
    known = {
        "name": "D600",
        "devId": KNOWN_DEVICE_ID,
        "localKey": "knownlocalkey830p",
        "uuid": KNOWN_UUID,
        "productName": "not-the-string-830P",
        "category": "sd",
    }
    cfg = discover_830p(
        "user@example.com",
        "pw",
        http_post=_oem_http([other, known]),
    )
    assert cfg["device_id"] == KNOWN_DEVICE_ID
    assert cfg["local_key"] == "knownlocalkey830p"


def test_ha_maps_no_device_only_when_matcher_finds_nothing() -> None:
    from pathlib import Path

    from proscenic_830p.oem_cloud import ProscenicOemError, pick_vacuum

    de = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "proscenic_830p"
        / "translations"
        / "de.json"
    ).read_text(encoding="utf-8")
    assert "Kein 830P auf diesem ProscenicHome-Konto" in de
    assert pick_vacuum([map_cloud_device(PLUG)]) is None
    try:
        discover_830p("user@example.com", "pw", http_post=_oem_http([PLUG]))
    except ProscenicOemError as exc:
        assert "no Proscenic 830P" in str(exc)
    else:
        raise AssertionError("expected ProscenicOemError")


def test_find_host_for_known_gwid() -> None:
    scan = lambda: {
        "192.168.178.63": {"ip": "192.168.178.63", "gwId": KNOWN_DEVICE_ID, "version": "3.3"}
    }
    assert find_host_for_gw_id(KNOWN_DEVICE_ID, scan=scan) == "192.168.178.63"
