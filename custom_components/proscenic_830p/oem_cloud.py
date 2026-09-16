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
    return _plain_rsa_encrypt(int(modulus_str), int(exponent_str), passwd_hash).hex()


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
    ) -> None:
        self._username = username
        self._password = password
        self._endpoint = f"https://a1.tuya{region}.com/api.json"
        self._http_post = http_post
        self._sid: str | None = None

    def login(self) -> str:
        token_info = self._api(
            "tuya.m.user.email.token.create",
            {"countryCode": "", "email": self._username},
            requires_sid=False,
        )
        login_info = self._api(
            "tuya.m.user.email.password.login",
            {
                "countryCode": "",
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
        self._sid = login_info["sid"]
        return self._sid

    def list_devices(self) -> list[CloudDevice]:
        devices: list[CloudDevice] = []
        groups = self._api("tuya.m.location.list") or []
        for group in groups:
            raw_list = self._api(
                "tuya.m.my.group.device.list", extra_params={"gid": group["groupId"]}
            ) or []
            for raw in raw_list:
                mapped = map_cloud_device(raw)
                if mapped.device_id:
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
            if code in {"USER_PASSWD_WRONG", "USER_SESSION_INVALID"}:
                raise InvalidAuthentication(str(msg))
            raise ProscenicOemError(f"{msg} ({code})")
        return body.get("result")

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
) -> dict[str, str]:
    """Login to ProscenicHome, return LAN config (password is not returned)."""
    from .constants import KNOWN_DEVICE_ID, KNOWN_UUID  # noqa: PLC0415

    api = ProscenicOemApi(email, password, region=region, http_post=http_post)
    api.login()
    found = pick_vacuum(
        api.list_devices(),
        known_id=device_id or KNOWN_DEVICE_ID,
        known_uuid=uuid or KNOWN_UUID,
    )
    if found is None:
        raise ProscenicOemError("no Proscenic 830P on this account")
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
