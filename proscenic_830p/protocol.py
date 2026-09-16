"""Tuya 3.3 / port 6668 command and status codecs for the Proscenic 830P.

Datapoint IDs match the 8xx family used by edenhaus/ha-prosenic (Model 830
confirmed) and make-all tuya-local's 850T profile. The 790T robotbona
protocol (ports 8888 / 10684) is not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import Mapping


class Command(Enum):
    START = "start"
    PAUSE = "pause"
    STOP = "stop"
    DOCK = "dock"
    SMART = "smart"
    WALL_FOLLOW = "wall_follow"
    SINGLE_ROOM = "single_room"
    SPOT = "spot"
    MOP = "mop"


class FanSpeed(Enum):
    ECO = "ECO"
    NORMAL = "normal"
    STRONG = "strong"


class Fault(IntFlag):
    NO_ERROR = 0
    SIDE_BRUSH = 1
    ROLLER_BRUSH = 2
    LEFT_WHEEL = 4
    RIGHT_WHEEL = 8
    DUST_BIN = 16
    OFF_GROUND = 32
    COLLISION_SENSOR = 64
    WATER_TANK = 128
    VIRTUAL_WALL = 256
    TRAPPED = 512
    UNKNOWN = 1024


class WorkState(Enum):
    STAND_BY = 0
    CLEAN_SMART = 1
    MOPPING = 2
    CLEAN_WALL_FOLLOW = 3
    GOING_CHARGING = 4
    CHARGING = 5
    IDLE = 6
    PAUSE = 7
    CLEAN_SINGLE = 8
    REMOTE = 9


class Direction(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    TURN_LEFT = "turnleft"
    TURN_RIGHT = "turnright"
    STOP = "stop"


DP_POWER = "1"
DP_FAULT = "11"
DP_MODE = "25"
DP_DIRECTION = "26"
DP_FAN = "27"
DP_STATE = "38"
DP_BATTERY = "39"
DP_CLEAN_RECORD = "40"
DP_CLEAN_AREA = "41"
DP_CLEAN_TIME = "42"
DP_SWEEP_OR_MOP = "49"

# 830 firmware spelling; 850T yaml uses "spiral". Encode the 830 value.
SPOT_MODE_VALUE = "sprial"

_MODE_VALUES: dict[Command, str] = {
    Command.START: "smart",
    Command.SMART: "smart",
    Command.DOCK: "chargego",
    Command.WALL_FOLLOW: "wallfollow",
    Command.SINGLE_ROOM: "single",
    Command.SPOT: SPOT_MODE_VALUE,
    Command.MOP: "mop",
}

_HA_STATE = {
    WorkState.STAND_BY: "idle",
    WorkState.CLEAN_SMART: "cleaning",
    WorkState.MOPPING: "cleaning",
    WorkState.CLEAN_WALL_FOLLOW: "cleaning",
    WorkState.GOING_CHARGING: "returning",
    WorkState.CHARGING: "docked",
    WorkState.IDLE: "idle",
    WorkState.PAUSE: "paused",
    WorkState.CLEAN_SINGLE: "cleaning",
    WorkState.REMOTE: "cleaning",
}


@dataclass(frozen=True)
class VacuumStatus:
    battery: int | None
    work_state: WorkState | None
    fan: FanSpeed | None
    faults: Fault
    mop_equipped: bool
    cleaned_area: int | None
    clean_time_min: int | None
    raw: dict[str, object]


def encode_command(command: Command, *, last_mode: str | None = None) -> dict[str, str]:
    if command is Command.STOP:
        return {DP_DIRECTION: Direction.STOP.value}
    if command is Command.PAUSE:
        return {DP_MODE: last_mode or "smart"}
    try:
        return {DP_MODE: _MODE_VALUES[command]}
    except KeyError as exc:
        raise ValueError(f"unsupported command {command}") from exc


def encode_fan(fan: FanSpeed) -> dict[str, str]:
    return {DP_FAN: fan.value}


def encode_direction(direction: str) -> dict[str, str]:
    parsed = Direction(direction)
    return {DP_DIRECTION: parsed.value}


def decode_status(dps: Mapping[object, object]) -> VacuumStatus:
    normalized = {str(key): value for key, value in dps.items()}
    faults = Fault(int(normalized.get(DP_FAULT, 0) or 0))
    work_state = None
    if DP_STATE in normalized and normalized[DP_STATE] not in (None, ""):
        work_state = WorkState(int(normalized[DP_STATE]))
    fan = None
    if DP_FAN in normalized and normalized[DP_FAN] not in (None, ""):
        try:
            fan = FanSpeed(str(normalized[DP_FAN]))
        except ValueError:
            fan = None
    mop_raw = normalized.get(DP_SWEEP_OR_MOP)
    mop_equipped = str(mop_raw) == "mop" if mop_raw is not None else False
    battery = _optional_int(normalized.get(DP_BATTERY))
    cleaned_area = _optional_int(normalized.get(DP_CLEAN_AREA))
    clean_time_min = _optional_int(normalized.get(DP_CLEAN_TIME))
    return VacuumStatus(
        battery=battery,
        work_state=work_state,
        fan=fan,
        faults=faults,
        mop_equipped=mop_equipped,
        cleaned_area=cleaned_area,
        clean_time_min=clean_time_min,
        raw=normalized,
    )


def ha_state(status: VacuumStatus) -> str:
    if status.faults is not Fault.NO_ERROR:
        return "error"
    if status.work_state is None:
        return "unknown"
    return _HA_STATE.get(status.work_state, "unknown")


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
