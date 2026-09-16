"""Home Assistant vacuum platform must call the same command mapping as protocol tests."""

from __future__ import annotations

from proscenic_830p.controller import VacuumController
from proscenic_830p.ha_vacuum import Proscenic830PVacuum, build_vacuum
from proscenic_830p.protocol import Command, FanSpeed, encode_command, encode_fan


def test_controller_start_pause_stop_dock_modes_fan(dps_payloads: dict) -> None:
    sent: list[dict] = []
    ctl = VacuumController(send_dps=sent.append)
    expected = dps_payloads["commands"]

    assert ctl.start() == expected["start"]
    assert ctl.pause() == expected["pause_resume_smart"]
    assert ctl.stop() == expected["stop"]
    assert ctl.dock() == expected["dock"]
    assert ctl.wall_follow() == expected["wall_follow"]
    assert ctl.single_room() == expected["single_room"]
    assert ctl.spot() == expected["spot"]
    assert ctl.mop() == expected["mop"]
    assert ctl.set_fan("ECO") == expected["fan_eco"]
    assert sent[0] == encode_command(Command.START)
    assert sent[3] == encode_command(Command.DOCK)
    assert sent[6] == encode_command(Command.SPOT)
    assert sent[-1] == encode_fan(FanSpeed.ECO)


def test_ha_entity_start_dock_spot_use_protocol_mapping() -> None:
    sent: list[dict] = []
    entity = build_vacuum("830P", send_dps=sent.append)
    entity.start()
    assert sent[-1] == encode_command(Command.START)
    entity.return_to_base()
    assert sent[-1] == encode_command(Command.DOCK)
    entity.clean_spot()
    assert sent[-1] == encode_command(Command.SPOT)
    entity.pause()
    # Pause re-issues the last cleaning mode (830P Tuya has no dedicated pause DP).
    assert sent[-1] == encode_command(Command.SPOT)
    entity.stop()
    assert sent[-1] == encode_command(Command.STOP)
    entity.set_fan_speed("strong")
    assert sent[-1] == encode_fan(FanSpeed.STRONG)


def test_ha_entity_is_the_platform_class() -> None:
    sent: list[dict] = []
    entity = Proscenic830PVacuum(name="830P", controller=VacuumController(sent.append))
    entity.start()
    assert sent == [encode_command(Command.START)]


def test_entity_status_from_dps_fixture(dps_payloads: dict) -> None:
    entity = build_vacuum("830P", send_dps=lambda dps: None)
    entity.apply_status(dps_payloads["status_smart_cleaning"])
    assert entity.state == "cleaning"
    assert entity.battery_level == 76
    assert entity.fan_speed == "normal"
    entity.apply_status(dps_payloads["status_fault_bumper"])
    assert entity.state == "error"


def test_async_setup_platform_mocked_hass_uses_protocol_mapping() -> None:
    import asyncio
    from unittest.mock import patch

    from proscenic_830p.ha_vacuum import async_setup_platform

    added: list = []
    captured: dict = {}

    class FakeAdapter:
        def __init__(self, *args, **kwargs) -> None:
            self.sent: list[dict] = []
            captured["adapter"] = self

        def send_dps(self, dps) -> None:
            self.sent.append(dict(dps))

        def status_dps(self) -> dict:
            return {"38": 5, "39": 100, "11": 0}

    def add_entities(entities, update_before_add=False) -> None:
        added.extend(entities)

    with patch("proscenic_830p.ha_vacuum.TuyaLanAdapter", FakeAdapter):
        asyncio.run(
            async_setup_platform(
                hass={},
                config={
                    "host": "192.168.1.50",
                    "device_id": "abc",
                    "local_key": "0123456789abcdef",
                    "name": "830P",
                },
                async_add_entities=add_entities,
            )
        )

    entity = added[0]
    entity.start()
    entity.return_to_base()
    entity.clean_spot()
    sent = captured["adapter"].sent
    assert sent == [
        encode_command(Command.START),
        encode_command(Command.DOCK),
        encode_command(Command.SPOT),
    ]


def test_custom_component_platform_reexports_same_class() -> None:
    from custom_components.proscenic_830p.vacuum import (  # noqa: PLC0415
        Proscenic830PVacuum as PlatformVacuum,
        build_vacuum as platform_build,
    )

    sent: list[dict] = []
    entity = platform_build("830P", send_dps=sent.append)
    assert isinstance(entity, PlatformVacuum)
    entity.start()
    entity.return_to_base()
    entity.clean_spot()
    assert sent == [
        encode_command(Command.START),
        encode_command(Command.DOCK),
        encode_command(Command.SPOT),
    ]
