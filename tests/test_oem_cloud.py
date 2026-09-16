from proscenic_830p.adapter import find_host_for_gw_id
from proscenic_830p.constants import KNOWN_DEVICE_ID, KNOWN_MAC, KNOWN_UUID
from proscenic_830p.oem_cloud import (
    InvalidAuthentication,
    MfaRequired,
    PasswordLocked,
    ProscenicOemApi,
    RateLimited,
    as_list,
    discover_830p,
    encrypt_password_pkcs1,
    map_cloud_device,
    sign_request,
)

# 1024-bit test RSA public key (e=65537). Fixtures only; not a live secret.
TEST_RSA_N = "137841994063388344446086203280754198666831192589101071969244430529477018791896457250730707560418431636474645430082899644012591478071279971035909890261529335771005777190369507559830058327341202479892500938549090426087041767862654572851241652062735735276802442549310795347935382269188184725421725453188048483451"
TEST_RSA_E = "65537"
TEST_PBKEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDESyPQ7eBL/ROR6xsZA0CAql7bdQp6TK6SqgbgTJD3wZopwuknvWFZJAYdp6O929HLwA5wGO5J20xHhVP0CZB1QxrzwSBdXV1t0v5xRPb030niN38jdY2cU6QxULndN1NN2FJ72u14WrWrBdxNrmSsSvmuk908B+LahDkt0WH0ewIDAQAB"
TEST_TOKEN = {
    "publicKey": TEST_RSA_N,
    "exponent": TEST_RSA_E,
    "pbKey": TEST_PBKEY,
    "token": "tok",
}

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


def _login_ok(action: str):
    if action == "thing.m.user.username.token.get":
        return {"success": True, "result": TEST_TOKEN}
    if action in (
        "thing.m.user.email.password.login",
        "thing.m.user.mobile.password.login",
        "tuya.m.user.email.password.login",
        "tuya.m.user.mobile.password.login",
    ):
        return {"success": True, "result": {"sid": "sid-1"}}
    if action in (
        "tuya.m.user.email.token.create",
        "tuya.m.user.mobile.token.create",
    ):
        return {"success": True, "result": TEST_TOKEN}
    return None


def test_oem_login_and_find_830p() -> None:
    calls: list[str] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        calls.append(action)
        login = _login_ok(action)
        if login is not None:
            return login
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
    assert "thing.m.user.email.password.login" in calls


def test_rate_limit_is_not_no_device_and_does_not_spray_countries() -> None:
    calls: list[str] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        calls.append(action)
        if action == "thing.m.user.username.token.get":
            return {
                "success": False,
                "errorCode": "REQUEST_TOO_FREQUENTLY_PLEASE_TRY_AGAIN_LATER",
                "errorMsg": "Requests are too frequent. Please try again later",
            }
        raise AssertionError(action)

    try:
        discover_830p("user@example.com", "pw", http_post=http_post)
    except RateLimited as exc:
        assert "TOO_FREQUENT" in str(exc).upper() or "frequent" in str(exc).lower()
    else:
        raise AssertionError("expected RateLimited")
    assert calls.count("thing.m.user.username.token.get") == 1
    assert "thing.m.user.email.password.login" not in calls


def test_login_sends_german_country_code_on_email() -> None:
    import json

    seen: list[tuple[str, str]] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        payload = json.loads(data["postData"]) if data and data.get("postData") else {}
        seen.append((action, str(payload.get("countryCode", ""))))
        login = _login_ok(action)
        if login is not None:
            return login
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {"success": True, "result": [SCHLURP_D600]}
        raise AssertionError(action)

    discover_830p("tommyra@gmx.de", "pw", http_post=http_post, country_code="49")
    assert ("thing.m.user.username.token.get", "49") in seen
    assert ("thing.m.user.email.password.login", "49") in seen


def test_phone_username_uses_mobile_login() -> None:
    import json

    actions: list[str] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        actions.append(action)
        payload = json.loads(data["postData"]) if data and data.get("postData") else {}
        if action == "thing.m.user.username.token.get":
            assert payload.get("countryCode") == "49"
            assert payload.get("username") == "17612345678"
            return {"success": True, "result": TEST_TOKEN}
        if action == "thing.m.user.mobile.password.login":
            assert payload.get("mobile") == "17612345678"
            return {"success": True, "result": {"sid": "sid-1"}}
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {"success": True, "result": [SCHLURP_D600]}
        raise AssertionError(action)

    cfg = discover_830p("0176 12345678", "pw", http_post=http_post, country_code="49")
    assert cfg["name"] == "schlurp"
    assert "thing.m.user.username.token.get" in actions
    assert "thing.m.user.mobile.password.login" in actions
    assert "thing.m.user.email.password.login" not in actions


def test_oem_wrong_password() -> None:
    def http_post(url, params=None, data=None):
        if params["a"] == "thing.m.user.username.token.get":
            return {"success": True, "result": TEST_TOKEN}
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


def test_password_lockout_is_password_locked_not_generic() -> None:
    def http_post(url, params=None, data=None):
        action = params["a"]
        if action in (
            "tuya.m.user.email.token.create",
            "thing.m.user.username.token.get",
        ):
            return {"success": True, "result": TEST_TOKEN}
        return {
            "success": False,
            "errorCode": "USER_PASSWD_ERROR_TIMES_TOO_MANY_1",
            "errorMsg": "You have entered too many wrong passwords. Please try again 5 minutes later.",
        }

    try:
        discover_830p("user@example.com", "pw", http_post=http_post)
    except PasswordLocked as exc:
        assert "5 minutes" in str(exc).lower() or "TOO_MANY" in str(exc).upper()
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"expected PasswordLocked, got {type(exc).__name__}: {exc}")
    raise AssertionError("expected PasswordLocked")


def test_discover_830p_returns_lan_config_without_password() -> None:
    def http_post(url, params=None, data=None):
        action = params["a"]
        login = _login_ok(action)
        if login is not None:
            return login
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
        login = _login_ok(action)
        if login is not None:
            return login
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {"success": True, "result": devices}
        raise AssertionError(action)

    return http_post


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


def test_as_list_unwraps_nested_group_and_device_payloads() -> None:
    assert as_list([{"groupId": "g1"}])[0]["groupId"] == "g1"
    assert as_list({"groupList": [{"id": "g1"}]})[0]["id"] == "g1"
    assert as_list({"devices": [SCHLURP_D600]})[0]["name"] == "schlurp"
    assert as_list({"list": [SCHLURP_D600]})[0]["devId"] == SCHLURP_D600["devId"]
    assert as_list(None) == []


def test_discover_nested_home_and_life_device_list() -> None:
    def http_post(url, params=None, data=None):
        action = params["a"]
        login = _login_ok(action)
        if login is not None:
            return login
        if action == "tuya.m.location.list":
            return {"success": True, "result": {"groupList": [{"id": "home-1"}]}}
        if action == "tuya.m.my.group.device.list":
            return {
                "success": False,
                "errorCode": "PERMISSION_DENIED",
                "errorMsg": "nope",
            }
        if action == "m.life.my.group.device.list":
            assert params.get("gid") == "home-1"
            return {"success": True, "result": {"devices": [SCHLURP_D600]}}
        raise AssertionError(action)

    cfg = discover_830p("user@example.com", "pw", http_post=http_post)
    assert cfg["local_key"] == "schlurplocalkey99"
    assert cfg["name"] == "schlurp"


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


def test_pkcs1_ciphertext_matches_modulus_and_is_nondeterministic() -> None:
    first = encrypt_password_pkcs1(TEST_RSA_N, TEST_RSA_E, "pw")
    second = encrypt_password_pkcs1(TEST_RSA_N, TEST_RSA_E, "pw")
    key_bytes = (int(TEST_RSA_N).bit_length() + 7) // 8
    assert len(bytes.fromhex(first)) == key_bytes
    assert first != second


def test_modern_email_login_uses_thing_token_v2() -> None:
    import json

    seen: list[tuple[str, str]] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        payload = json.loads(data["postData"]) if data and data.get("postData") else {}
        seen.append((action, str(params.get("v", "")), str(payload.get("countryCode", ""))))
        if action == "thing.m.user.username.token.get":
            assert payload.get("username") == "tommyra@gmx.de"
            assert payload.get("isUid") is False
            return {"success": True, "result": TEST_TOKEN}
        if action == "thing.m.user.email.password.login":
            assert payload.get("ifencrypt") == 1
            assert payload.get("token") == "tok"
            assert len(str(payload.get("passwd", ""))) >= 256
            return {"success": True, "result": {"sid": "sid-thing"}}
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {"success": True, "result": [SCHLURP_D600]}
        raise AssertionError(action)

    cfg = discover_830p("tommyra@gmx.de", "pw", http_post=http_post, country_code="49")
    assert cfg["name"] == "schlurp"
    assert ("thing.m.user.username.token.get", "2.0", "49") in seen
    assert ("thing.m.user.email.password.login", "3.0", "49") in seen
    assert not any(action.startswith("tuya.m.user.") for action, _v, _cc in seen)


def test_wrong_password_on_modern_login_does_not_retry_legacy() -> None:
    actions: list[str] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        actions.append(action)
        if action == "thing.m.user.username.token.get":
            return {"success": True, "result": TEST_TOKEN}
        if action == "thing.m.user.email.password.login":
            return {
                "success": False,
                "errorCode": "USER_PASSWD_WRONG",
                "errorMsg": "Incorrect account or password",
            }
        raise AssertionError(f"unexpected extra call {action}")

    try:
        discover_830p("user@example.com", "pw", http_post=http_post)
    except InvalidAuthentication:
        pass
    else:
        raise AssertionError("expected InvalidAuthentication")
    assert actions.count("thing.m.user.email.password.login") == 1
    assert "tuya.m.user.email.password.login" not in actions
    assert "tuya.m.user.email.token.create" not in actions


def test_legacy_login_when_thing_token_api_missing() -> None:
    actions: list[str] = []

    def http_post(url, params=None, data=None):
        action = params["a"]
        actions.append(action)
        if action == "thing.m.user.username.token.get":
            return {
                "success": False,
                "errorCode": "API_OR_API_VERSION_WRONG",
                "errorMsg": "nope",
            }
        if action == "tuya.m.user.email.token.create":
            return {"success": True, "result": TEST_TOKEN}
        if action == "tuya.m.user.email.password.login":
            return {"success": True, "result": {"sid": "sid-legacy"}}
        if action == "tuya.m.location.list":
            return {"success": True, "result": [{"groupId": "g1"}]}
        if action == "tuya.m.my.group.device.list":
            return {"success": True, "result": [SCHLURP_D600]}
        raise AssertionError(action)

    cfg = discover_830p("user@example.com", "pw", http_post=http_post)
    assert cfg["local_key"] == "schlurplocalkey99"
    assert "tuya.m.user.email.password.login" in actions


def test_mfa_need_send_code_is_mfa_required() -> None:
    sent_mfa = {"n": 0}

    def http_post(url, params=None, data=None):
        action = params["a"]
        if action == "thing.m.user.username.token.get":
            return {"success": True, "result": TEST_TOKEN}
        if action == "thing.m.user.email.password.login":
            return {
                "success": False,
                "errorCode": "MFA_NEED_SEND_CODE",
                "errorMsg": "need mfa",
            }
        if action == "thing.m.user.username.mfa.code.get":
            sent_mfa["n"] += 1
            return {
                "success": True,
                "result": {"countryCode": "49", "email": "user@example.com"},
            }
        raise AssertionError(action)

    try:
        discover_830p("user@example.com", "pw", http_post=http_post)
    except MfaRequired:
        assert sent_mfa["n"] == 1
        return
    raise AssertionError("expected MfaRequired")


def test_ha_maps_password_lockout_string() -> None:
    from pathlib import Path

    de = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "proscenic_830p"
        / "translations"
        / "de.json"
    ).read_text(encoding="utf-8")
    assert "password_locked" in de
    assert "5 Minuten" in de
