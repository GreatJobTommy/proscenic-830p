"""HA-independent vacuum controller over encoded Tuya DPs."""

from __future__ import annotations

from typing import Callable, Mapping

from .protocol import (
    Command,
    FanSpeed,
    VacuumStatus,
    decode_status,
    encode_command,
    encode_direction,
    encode_fan,
)

SendDps = Callable[[Mapping[str, object]], object]
StatusFn = Callable[[], Mapping[object, object]]


class VacuumController:
    def __init__(self, send_dps: SendDps, status_fn: StatusFn | None = None) -> None:
        self._send_dps = send_dps
        self._status_fn = status_fn
        self.last_mode: str | None = None

    def _send(self, dps: dict[str, object]) -> dict[str, object]:
        if DP_MODE := dps.get("25"):
            self.last_mode = str(DP_MODE)
        self._send_dps(dps)
        return dps

    def start(self) -> dict[str, object]:
        return self._send(encode_command(Command.START))

    def pause(self) -> dict[str, object]:
        return self._send(encode_command(Command.PAUSE, last_mode=self.last_mode))

    def stop(self) -> dict[str, object]:
        return self._send(encode_command(Command.STOP))

    def dock(self) -> dict[str, object]:
        return self._send(encode_command(Command.DOCK))

    def smart(self) -> dict[str, object]:
        return self._send(encode_command(Command.SMART))

    def wall_follow(self) -> dict[str, object]:
        return self._send(encode_command(Command.WALL_FOLLOW))

    def single_room(self) -> dict[str, object]:
        return self._send(encode_command(Command.SINGLE_ROOM))

    def spot(self) -> dict[str, object]:
        return self._send(encode_command(Command.SPOT))

    def mop(self) -> dict[str, object]:
        return self._send(encode_command(Command.MOP))

    def set_fan(self, speed: str | FanSpeed) -> dict[str, object]:
        fan = speed if isinstance(speed, FanSpeed) else FanSpeed(speed)
        return self._send(encode_fan(fan))

    def direction(self, direction: str) -> dict[str, object]:
        return self._send(encode_direction(direction))

    def refresh(self) -> VacuumStatus | None:
        if self._status_fn is None:
            return None
        return decode_status(self._status_fn())
