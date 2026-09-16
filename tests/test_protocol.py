"""Drive the shipped 830P command/status codecs against recorded DP fixtures."""

from __future__ import annotations

from proscenic_830p.constants import (
    FIRMWARE_MAIN,
    FIRMWARE_MCU,
    TUYA_PORT,
    TUYA_VERSION,
    WIFI_BAND_GHZ,
)
from proscenic_830p.protocol import (
    Command,
    Fault,
    FanSpeed,
    WorkState,
    decode_status,
    encode_command,
    encode_direction,
    encode_fan,
    ha_state,
)


def test_firmware_and_radio_constants() -> None:
    assert FIRMWARE_MAIN == "1.0.3"
    assert FIRMWARE_MCU == "1.4.3"
    assert WIFI_BAND_GHZ == 2.4
    assert TUYA_PORT == 6668
    assert TUYA_VERSION == 3.3


def test_encode_product_commands_match_fixtures(dps_payloads: dict) -> None:
    expected = dps_payloads["commands"]
    assert encode_command(Command.START) == expected["start"]
    assert encode_command(Command.PAUSE, last_mode="smart") == expected["pause_resume_smart"]
    assert encode_command(Command.STOP) == expected["stop"]
    assert encode_command(Command.DOCK) == expected["dock"]
    assert encode_command(Command.SMART) == expected["smart"]
    assert encode_command(Command.WALL_FOLLOW) == expected["wall_follow"]
    assert encode_command(Command.SINGLE_ROOM) == expected["single_room"]
    assert encode_command(Command.SPOT) == expected["spot"]
    assert encode_command(Command.MOP) == expected["mop"]
    assert encode_fan(FanSpeed.ECO) == expected["fan_eco"]
    assert encode_fan(FanSpeed.NORMAL) == expected["fan_normal"]
    assert encode_fan(FanSpeed.STRONG) == expected["fan_strong"]


def test_spot_uses_830p_firmware_spelling_sprial() -> None:
    # 8xx Tuya firmware (confirmed on 830) uses the misspelling "sprial".
    assert encode_command(Command.SPOT) == {"25": "sprial"}
    assert encode_command(Command.SPOT)["25"] != "spiral"


def test_decode_status_cleaning_battery_and_fan(dps_payloads: dict) -> None:
    status = decode_status(dps_payloads["status_smart_cleaning"])
    assert status.battery == 76
    assert status.work_state is WorkState.CLEAN_SMART
    assert status.fan is FanSpeed.NORMAL
    assert status.faults is Fault.NO_ERROR
    assert status.mop_equipped is False
    assert status.cleaned_area == 12
    assert status.clean_time_min == 18
    assert ha_state(status) == "cleaning"


def test_decode_modes_and_work_states(dps_payloads: dict) -> None:
    paused = decode_status(dps_payloads["status_paused"])
    assert paused.work_state is WorkState.PAUSE
    assert paused.fan is FanSpeed.ECO
    assert ha_state(paused) == "paused"

    docked = decode_status(dps_payloads["status_docked"])
    assert docked.work_state is WorkState.CHARGING
    assert docked.battery == 100
    assert ha_state(docked) == "docked"

    returning = decode_status(dps_payloads["status_returning"])
    assert returning.work_state is WorkState.GOING_CHARGING
    assert ha_state(returning) == "returning"

    wall = decode_status(dps_payloads["status_wall_follow"])
    assert wall.work_state is WorkState.CLEAN_WALL_FOLLOW
    assert ha_state(wall) == "cleaning"

    single = decode_status(dps_payloads["status_single_room"])
    assert single.work_state is WorkState.CLEAN_SINGLE
    assert ha_state(single) == "cleaning"

    mop = decode_status(dps_payloads["status_mopping"])
    assert mop.work_state is WorkState.MOPPING
    assert mop.mop_equipped is True
    assert ha_state(mop) == "cleaning"


def test_decode_fault_bits(dps_payloads: dict) -> None:
    bumper = decode_status(dps_payloads["status_fault_bumper"])
    assert Fault.COLLISION_SENSOR in bumper.faults
    assert ha_state(bumper) == "error"

    cliff = decode_status(dps_payloads["status_fault_cliff"])
    assert Fault.OFF_GROUND in cliff.faults
    assert ha_state(cliff) == "error"

    trapped = decode_status(dps_payloads["status_fault_trapped"])
    assert Fault.TRAPPED in trapped.faults

    dust = decode_status(dps_payloads["status_fault_dustbin"])
    assert Fault.DUST_BIN in dust.faults

    wheels = decode_status(dps_payloads["status_fault_wheels"])
    assert Fault.LEFT_WHEEL in wheels.faults
    assert Fault.RIGHT_WHEEL in wheels.faults

    brushes = decode_status(dps_payloads["status_fault_brushes"])
    assert Fault.SIDE_BRUSH in brushes.faults
    assert Fault.ROLLER_BRUSH in brushes.faults

    tank = decode_status(dps_payloads["status_fault_water_tank"])
    assert Fault.WATER_TANK in tank.faults
    assert ha_state(tank) == "error"


def test_decode_accepts_int_or_str_dp_keys() -> None:
    status = decode_status({38: "1", 39: "87", 11: "0", 27: "strong"})
    assert status.battery == 87
    assert status.work_state is WorkState.CLEAN_SMART
    assert status.fan is FanSpeed.STRONG


def test_encode_direction_overlay() -> None:
    assert encode_direction("forward") == {"26": "forward"}
    assert encode_direction("backward") == {"26": "backward"}
    assert encode_direction("turnleft") == {"26": "turnleft"}
    assert encode_direction("turnright") == {"26": "turnright"}
    assert encode_direction("stop") == {"26": "stop"}
