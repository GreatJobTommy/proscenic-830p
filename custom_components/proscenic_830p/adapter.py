"""LAN transport for the 830P.

Prefers Tuya 3.3 on TCP 6668. Ports 8888 / 10684 are probed only as a
robotbona (790T-style) fallback when 6668 is closed.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

from .constants import ROBOTBONA_PORTS, TUYA_PORT, TUYA_VERSION
from .protocol import decode_status

Opener = Callable[..., object]


class ProtocolKind(Enum):
    TUYA = "tuya"
    ROBOTBONA = "robotbona"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProbeResult:
    kind: ProtocolKind
    port: int | None
    host: str | None = None


def probe_lan(
    host: str,
    opener: Opener | None = None,
    timeout: float = 0.5,
) -> ProbeResult:
    """Try Tuya 6668 first, then robotbona ports. Never assumes 790T."""
    connect = opener or socket.create_connection
    for port in (TUYA_PORT, *ROBOTBONA_PORTS):
        conn = None
        try:
            conn = connect((host, port), timeout=timeout)
        except OSError:
            continue
        else:
            closer = getattr(conn, "close", None)
            if callable(closer):
                try:
                    closer()
                except OSError:
                    pass
            kind = (
                ProtocolKind.TUYA if port == TUYA_PORT else ProtocolKind.ROBOTBONA
            )
            return ProbeResult(kind=kind, port=port, host=host)
    return ProbeResult(kind=ProtocolKind.UNKNOWN, port=None, host=host)


def find_host_for_gw_id(
    gw_id: str,
    scan: Callable[[], Mapping[str, Mapping[str, object]]] | None = None,
) -> str | None:
    """Match a tinytuya LAN scan entry to a Tuya gwId (device_id)."""
    if scan is None:
        import tinytuya  # noqa: PLC0415

        devices = tinytuya.deviceScan(maxretry=2)
    else:
        devices = scan()
    for ip, info in devices.items():
        if str(info.get("gwId") or info.get("id") or "") == gw_id:
            return str(info.get("ip") or ip)
    return None


class TuyaLanAdapter:
    """Thin tinytuya wrapper. One LAN client at a time (Tuya socket limit)."""

    def __init__(
        self,
        device_id: str,
        host: str,
        local_key: str,
        version: float = TUYA_VERSION,
        device_factory: Callable[..., object] | None = None,
    ) -> None:
        self.device_id = device_id
        self.host = host
        self.local_key = local_key
        self.version = version
        self._device_factory = device_factory
        self._device: object | None = None

    def _connect(self) -> object:
        if self._device is not None:
            return self._device
        factory = self._device_factory
        if factory is None:
            import tinytuya  # noqa: PLC0415

            factory = tinytuya.OutletDevice
        device = factory(self.device_id, self.host, self.local_key)
        if hasattr(device, "set_version"):
            device.set_version(self.version)
        else:
            device.version = self.version
        self._device = device
        return device

    def send_dps(self, dps: Mapping[str, object]) -> None:
        device = self._connect()
        setter = getattr(device, "set_value")
        for key, value in dps.items():
            setter(int(key), value)

    def status_dps(self) -> dict[str, object]:
        device = self._connect()
        payload = getattr(device, "status")()
        dps = payload.get("dps", payload) if isinstance(payload, dict) else payload
        return {str(k): v for k, v in dict(dps).items()}

    def status(self):
        return decode_status(self.status_dps())
