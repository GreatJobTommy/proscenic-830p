"""LAN adapter prefers Tuya 6668 and exposes a robotbona probe hook."""

from __future__ import annotations

from proscenic_830p.adapter import ProtocolKind, probe_lan
from proscenic_830p.constants import ROBOTBONA_PORTS, TUYA_PORT


def test_probe_prefers_tuya_6668() -> None:
    opened: list[tuple[str, int]] = []

    def opener(address: tuple[str, int], timeout: float = 0.5):
        opened.append(address)
        if address[1] == TUYA_PORT:
            return object()
        raise OSError("closed")

    result = probe_lan("192.168.1.50", opener=opener)
    assert result.kind is ProtocolKind.TUYA
    assert result.port == TUYA_PORT
    assert opened[0] == ("192.168.1.50", TUYA_PORT)


def test_probe_falls_back_to_robotbona_ports() -> None:
    def opener(address: tuple[str, int], timeout: float = 0.5):
        if address[1] in ROBOTBONA_PORTS:
            return object()
        raise OSError("closed")

    result = probe_lan("192.168.1.50", opener=opener)
    assert result.kind is ProtocolKind.ROBOTBONA
    assert result.port in ROBOTBONA_PORTS


def test_probe_none_when_all_closed() -> None:
    def opener(address: tuple[str, int], timeout: float = 0.5):
        raise OSError("closed")

    result = probe_lan("192.168.1.50", opener=opener)
    assert result.kind is ProtocolKind.UNKNOWN
    assert result.port is None
