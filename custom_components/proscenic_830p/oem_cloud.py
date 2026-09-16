"""ProscenicHome OEM Tuya cloud: one-shot local_key fetch, then LAN only.

Uses the public Proscenic app client id/secret (same as tuya-uncover).
Password is never stored; only device_id + local_key + host are kept.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

PROSCENIC_CLIENT_ID = "ja9ntfcxcs8qg5sqdcfm"
PROSCENIC_SECRET = (
    "A_4vgq3tcqnam9drtvgam8hneqjprtjnf4_c5rkn5tga889whe5cd7pc9j387knwsuc"
)
USER_AGENT = "TY-UA=APP/Android/1.1.6/SDK/null"
API_VERSION = "1.0"
DEFAULT_REGION = "eu"
_DEVICE_LIST_ACTIONS = (
    "tuya.m.my.group.device.list",
    "m.life.my.group.device.list",
)
_HOME_LIST_ACTIONS = (
    "tuya.m.location.list",
    "m.life.home.list",
)

HttpPost = Callable[..., Any]


@dataclass(frozen=True)
class CloudDevice:
    name: str
    device_id: str
    local_key: str
    uuid: str
    product_id: str
    category: str
    dps: dict[str, Any]
    product_name: str = ""


class ProscenicOemError(Exception):
    pass


class InvalidAuthentication(ProscenicOemError):
    pass


class RateLimited(ProscenicOemError):
    pass


_RATE_LIMIT_CODES = {
    "REQUEST_TOO_FREQUENTLY_PLEASE_TRY_AGAIN_LATER",
    "REQUEST_TOO_FREQUENTLY",
    "REPEATED_REQUEST",
}


def _mobile_hash(data: str) -> str:
    prehash = hashlib.md5(data.encode("utf-8")).hexdigest()
    return prehash[8:16] + prehash[0:8] + prehash[24:32] + prehash[16:24]


def sign_request(secret: str, params: dict[str, str]) -> str:
    parts = []
    for key in sorted(params):
        if key == "gid":
            continue
        value = params[key]
        if key == "postData":
            value = _mobile_hash(value)
        parts.append(f"{key}={value}")
    payload = "||".join(parts)
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _plain_rsa_encrypt(modulus: int, exponent: int, message: bytes) -> bytes:
    message_int = int.from_bytes(message, "big")
    enc = pow(message_int, exponent, modulus)
    return enc.to_bytes(256, "big")


def encrypt_password(modulus_str: str, exponent_str: str, password: str) -> str:
    passwd_hash = hashlib.md5(password.encode("utf-8")).hexdigest().encode("utf-8")
    return _plain_rsa_encrypt(
        _parse_int(modulus_str), _parse_int(exponent_str), passwd_hash
    ).hex()


def _parse_int(value: str) -> int:
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        return int(text, 16)


def as_list(result: Any) -> list[Any]:
    """Unwrap OEM list payloads (bare list or {devices|list|groupList|...})."""
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in (
            "devices",
            "deviceList",
            "list",
            "groupList",
            "groups",
            "homes",
            "data",
            "infos",
        ):
            value = result.get(key)
            if isinstance(value, list):
                return value
        if any(k in result for k in ("devId", "id", "gwId", "groupId")):
            return [result]
    return []


def looks_like_email(username: str) -> bool:
    return "@" in username.strip()


def normalize_mobile(username: str, country_code: str) -> str:
    digits = "".join(c for c in username if c.isdigit())
    cc = "".join(c for c in country_code if c.isdigit())
    if cc and digits.startswith(cc):
        digits = digits[len(cc) :]
    return digits.lstrip("0")


def group_id_of(group: Any) -> str:
    if not isinstance(group, dict):
        return str(group)
    for key in ("groupId", "gid", "id", "homeId", "ownerId"):
        if group.get(key) not in (None, ""):
            return str(group[key])
    return ""


_VACUUM_CATEGORIES = {"sd"}
_VACUUM_HINTS = ("schlurp", "830p", "830", "d600", "saugroboter", "vacuum", "sweeper")


def map_cloud_device(raw: dict[str, Any]) -> CloudDevice:
    device_id = str(raw.get("devId") or raw.get("id") or raw.get("gwId") or "")
    local_key = str(raw.get("localKey") or raw.get("local_key") or raw.get("key") or "")
    return CloudDevice(
        name=str(raw.get("name") or ""),
        device_id=device_id,
        local_key=local_key,
        uuid=str(raw.get("uuid") or ""),
        product_id=str(raw.get("productId") or ""),
        category=str(raw.get("category") or ""),
        dps=dict(raw.get("dps") or {}),
        product_name=str(raw.get("productName") or raw.get("model") or ""),
    )


def is_vacuum_like(device: CloudDevice) -> bool:
    blob = " ".join(
        [
            device.name,
            device.product_name,
            device.product_id,
            device.category,
        ]
    ).lower()
    if device.category.lower() in _VACUUM_CATEGORIES:
        return True
    return any(hint in blob for hint in _VACUUM_HINTS)


def pick_vacuum(
    devices: list[CloudDevice],
    known_id: str | None = None,
    known_uuid: str | None = None,
) -> CloudDevice | None:
    """Prefer known LAN id/uuid, then schlurp/D600/830P/sweeper — not exact name 830P."""
    if known_id:
        for device in devices:
            if device.device_id == known_id and device.local_key:
                return device
    if known_uuid:
        for device in devices:
            if device.uuid == known_uuid and device.local_key:
                return device
    vacuums = [d for d in devices if d.local_key and is_vacuum_like(d)]
    if not vacuums:
        return None
    for device in vacuums:
        if "schlurp" in device.name.lower():
            return device
    for device in vacuums:
        if "d600" in (device.name + " " + device.product_name).lower():
            return device
    return vacuums[0]


class ProscenicOemApi:
    def __init__(
        self,
        username: str,
        password: str,
        region: str = DEFAULT_REGION,
        http_post: HttpPost | None = None,
        country_code: str = "49",
    ) -> None:
        self._username = username.strip()
        self._password = password
        self._country_code = (country_code or "49").strip().lstrip("+")
        self._endpoint = f"https://a1.tuya{region}.com/api.json"
        self._http_post = http_post
        self._sid: str | None = None

    def login(self) -> str:
        # German ProscenicHome accounts need countryCode 49; empty code
        # often comes back as USER_PASSWD_WRONG.
        if looks_like_email(self._username):
            self._sid = self._login_email(self._country_code)
        else:
            self._sid = self._login_mobile(self._country_code)
        return self._sid

    def _login_email(self, country_code: str) -> str:
        token_info = self._api(
            "tuya.m.user.email.token.create",
            {"countryCode": country_code, "email": self._username},
            requires_sid=False,
        )
        login_info = self._api(
            "tuya.m.user.email.password.login",
            {
                "countryCode": country_code,
                "email": self._username,
                "ifencrypt": 1,
                "options": '{"group": 1}',
                "passwd": encrypt_password(
                    token_info["publicKey"], token_info["exponent"], self._password
                ),
                "token": token_info["token"],
            },
            requires_sid=False,
        )
        return str(login_info["sid"])

    def _login_mobile(self, country_code: str) -> str:
        mobile = normalize_mobile(self._username, country_code)
        token_info = self._api(
            "tuya.m.user.mobile.token.create",
            {"countryCode": country_code, "mobile": mobile},
            requires_sid=False,
        )
        login_info = self._api(
            "tuya.m.user.mobile.password.login",
            {
                "countryCode": country_code,
                "mobile": mobile,
                "ifencrypt": 1,
                "options": '{"group": 1}',
                "passwd": encrypt_password(
                    token_info["publicKey"], token_info["exponent"], self._password
                ),
                "token": token_info["token"],
            },
            requires_sid=False,
        )
        return str(login_info["sid"])

    def list_devices(self) -> list[CloudDevice]:
        devices: list[CloudDevice] = []
        seen: set[str] = set()
        groups = []
        for action in _HOME_LIST_ACTIONS:
            groups = as_list(self._api_try(action))
            if groups:
                break
        gids = [gid for gid in (group_id_of(g) for g in groups) if gid]
        if not gids:
            gids = [""]
        for gid in gids:
            extra = {"gid": gid} if gid else None
            raw_list: list[Any] = []
            for action in _DEVICE_LIST_ACTIONS:
                raw_list = as_list(self._api_try(action, extra_params=extra))
                if raw_list:
                    break
            for raw in raw_list:
                if not isinstance(raw, dict):
                    continue
                mapped = map_cloud_device(raw)
                if mapped.device_id and mapped.device_id not in seen:
                    seen.add(mapped.device_id)
                    devices.append(mapped)
        return devices

    def find_830p(
        self, device_id: str | None = None, uuid: str | None = None
    ) -> CloudDevice | None:
        return pick_vacuum(self.list_devices(), known_id=device_id, known_uuid=uuid)

    def _api(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        extra_params: dict[str, str] | None = None,
        requires_sid: bool = True,
    ) -> Any:
        params: dict[str, str] = {
            "a": action,
            "clientId": PROSCENIC_CLIENT_ID,
            "v": API_VERSION,
            "time": str(int(time.time())),
        }
        if extra_params:
            params.update(extra_params)
        if requires_sid:
            if not self._sid:
                raise ProscenicOemError("login required")
            params["sid"] = self._sid
        data: dict[str, str] = {}
        if payload is not None:
            data["postData"] = json.dumps(payload, separators=(",", ":"))
        sign_source = {**params, **data}
        params["sign"] = sign_request(PROSCENIC_SECRET, sign_source)
        body = self._post(params, data)
        if not body.get("success"):
            code = body.get("errorCode")
            msg = body.get("errorMsg") or code or "oem api error"
            if code == "USER_PASSWD_WRONG":
                raise InvalidAuthentication(str(msg))
            if str(code) in _RATE_LIMIT_CODES:
                raise RateLimited(f"{msg} ({code})")
            raise ProscenicOemError(f"{msg} ({code})")
        return body.get("result")

    def _api_try(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        extra_params: dict[str, str] | None = None,
        requires_sid: bool = True,
    ) -> Any:
        try:
            return self._api(
                action,
                payload=payload,
                extra_params=extra_params,
                requires_sid=requires_sid,
            )
        except RateLimited:
            raise
        except ProscenicOemError:
            return None

    def _post(self, params: dict[str, str], data: dict[str, str]) -> dict[str, Any]:
        if self._http_post is not None:
            return self._http_post(self._endpoint, params=params, data=data)
        import requests  # noqa: PLC0415

        response = requests.post(
            self._endpoint,
            params=params,
            data=data,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


def discover_830p(
    email: str,
    password: str,
    region: str = DEFAULT_REGION,
    device_id: str | None = None,
    uuid: str | None = None,
    http_post: HttpPost | None = None,
    hosts_by_gwid: Mapping[str, str] | None = None,
    country_code: str = "49",
) -> dict[str, str]:
    """Login to ProscenicHome, return LAN config (password is not returned)."""
    from .constants import KNOWN_DEVICE_ID, KNOWN_UUID  # noqa: PLC0415

    api = ProscenicOemApi(
        email,
        password,
        region=region,
        http_post=http_post,
        country_code=country_code,
    )
    api.login()
    devices = api.list_devices()
    found = pick_vacuum(
        devices,
        known_id=device_id or KNOWN_DEVICE_ID,
        known_uuid=uuid or KNOWN_UUID,
    )
    if found is None:
        names = ", ".join(
            (d.name or d.product_name or d.device_id or "?") for d in devices
        ) or "none"
        raise ProscenicOemError(f"no Proscenic 830P on this account (saw: {names})")
    host = ""
    if hosts_by_gwid:
        host = hosts_by_gwid.get(found.device_id, "")
    return {
        "host": host,
        "device_id": found.device_id,
        "local_key": found.local_key,
        "uuid": found.uuid,
        "name": found.name,
    }
