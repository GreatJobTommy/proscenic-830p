"""Home Assistant vacuum entity that delegates to VacuumController.

Works without Home Assistant installed: tests and the CLI use this class
directly. When HA is present, async_setup_platform wires tinytuya LAN I/O.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .adapter import TuyaLanAdapter
from .kartierung_session import KartierungSession
from .map_image import render_occupancy_png
from .constants import FIRMWARE_MAIN, FIRMWARE_MCU, WIFI_BAND_GHZ
from .controller import VacuumController
from .protocol import FanSpeed, Fault, WorkState, decode_status, ha_state

SendDps = Callable[[Mapping[str, object]], object]

try:
    from homeassistant.components.vacuum import (  # type: ignore
        PLATFORM_SCHEMA as VACUUM_PLATFORM_SCHEMA,
        StateVacuumEntity,
        VacuumEntityFeature,
    )
    from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME  # type: ignore
    import homeassistant.helpers.config_validation as cv  # type: ignore
    import voluptuous as vol  # type: ignore

    PLATFORM_SCHEMA = VACUUM_PLATFORM_SCHEMA.extend(
        {
            vol.Required(CONF_HOST): cv.string,
            vol.Required(CONF_DEVICE_ID): cv.string,
            vol.Required("local_key"): vol.All(cv.string, vol.Length(min=15, max=16)),
            vol.Optional(CONF_NAME, default="Proscenic 830P"): cv.string,
        }
    )
    _HA = True
    _FEATURES = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.BATTERY
        | VacuumEntityFeature.CLEAN_SPOT
        | VacuumEntityFeature.SEND_COMMAND
    )
except ImportError:
    _HA = False
    PLATFORM_SCHEMA = None

    class StateVacuumEntity:  # type: ignore[no-redef]
        """Stand-in so the entity imports without Home Assistant."""

    class VacuumEntityFeature:  # type: ignore[no-redef]
        STATE = START = PAUSE = STOP = RETURN_HOME = FAN_SPEED = BATTERY = 0
        CLEAN_SPOT = SEND_COMMAND = 0

    _FEATURES = 0


class Proscenic830PVacuum(StateVacuumEntity):
    """Vacuum entity API used by HA and by tests."""

    _attr_should_poll = True
    _attr_supported_features = _FEATURES
    _attr_fan_speed_list = [item.value for item in FanSpeed]

    @property
    def should_poll(self) -> bool:
        session = getattr(self, "_session", None)
        return not (session is not None and session.running)

    def __init__(
        self,
        name: str,
        controller: VacuumController,
        unique_id: str | None = None,
        session: KartierungSession | None = None,
    ) -> None:
        super().__init__()
        self._attr_name = name
        self._controller = controller
        self._attr_unique_id = unique_id
        self._status = None
        self._available = True
        self._session = session
        self._kartierung_task: asyncio.Task | None = None
        self._map_rev = 0

    @property
    def name(self) -> str:
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        return self._attr_unique_id

    @property
    def available(self) -> bool:
        return self._available

    @property
    def supported_features(self) -> int:
        return self._attr_supported_features

    @property
    def fan_speed_list(self) -> list[str]:
        return list(self._attr_fan_speed_list)

    @property
    def controller(self) -> VacuumController:
        return self._controller

    def start(self) -> dict[str, object]:
        return self._controller.start()

    def pause(self) -> dict[str, object]:
        return self._controller.pause()

    def stop(self, **kwargs: Any) -> dict[str, object]:
        del kwargs
        return self._controller.stop()

    def return_to_base(self, **kwargs: Any) -> dict[str, object]:
        del kwargs
        return self._controller.dock()

    def clean_spot(self, **kwargs: Any) -> dict[str, object]:
        del kwargs
        return self._controller.spot()

    def set_fan_speed(self, fan_speed: str, **kwargs: Any) -> dict[str, object]:
        del kwargs
        return self._controller.set_fan(fan_speed)

    def wall_follow(self) -> dict[str, object]:
        return self._controller.wall_follow()

    def single_room(self) -> dict[str, object]:
        return self._controller.single_room()

    def mop(self) -> dict[str, object]:
        return self._controller.mop()

    def send_command(self, command: str, params: dict | None = None) -> dict[str, object]:
        del params
        key = command.lower().replace("-", "_")
        dispatch = {
            "start": self.start,
            "pause": self.pause,
            "stop": self.stop,
            "dock": self.return_to_base,
            "return_to_base": self.return_to_base,
            "smart": self._controller.smart,
            "wall_follow": self.wall_follow,
            "single_room": self.single_room,
            "spot": self.clean_spot,
            "clean_spot": self.clean_spot,
            "mop": self.mop,
        }
        try:
            return dispatch[key]()
        except KeyError as exc:
            raise ValueError(f"unsupported command {command}") from exc

    def apply_status(self, dps: Mapping[object, object]) -> None:
        self._status = decode_status(dps)
        self._available = True

    def update(self) -> None:
        try:
            status = self._controller.refresh()
            if status is not None:
                self._status = status
            self._available = True
        except Exception:
            self._available = False

    @property
    def state(self) -> str | None:
        if self._status is None:
            return None
        return ha_state(self._status)

    @property
    def battery_level(self) -> int | None:
        if self._status is None:
            return None
        return self._status.battery

    @property
    def fan_speed(self) -> str | None:
        if self._status is None or self._status.fan is None:
            return None
        return self._status.fan.value

    @property
    def entity_picture(self) -> str | None:
        if not self._map_rev:
            return None
        return f"/local/proscenic_830p_karte.png?v={self._map_rev}"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attrs: dict[str, object] = {
            "firmware_main": FIRMWARE_MAIN,
            "firmware_mcu": FIRMWARE_MCU,
            "wifi_ghz": WIFI_BAND_GHZ,
        }
        if self._session is not None:
            report = self._session.grid.report()
            attrs["kartierung"] = self._session.running
            attrs["kartierung_phase"] = self._session.phase
            attrs["kartierung_reason"] = self._session.reason
            attrs["occupied"] = report.occupied
            attrs["free"] = report.free
        if self._status is None:
            return attrs
        attrs["mop_equipped"] = self._status.mop_equipped
        attrs["faults"] = (
            self._status.faults.name
            if self._status.faults is not Fault.NO_ERROR
            else None
        )
        if self._status.cleaned_area is not None:
            attrs["cleaned_area"] = self._status.cleaned_area
        if self._status.clean_time_min is not None:
            attrs["cleaning_time"] = self._status.clean_time_min
        return attrs

    async def async_start(self) -> dict[str, object]:
        return self.start()

    async def async_pause(self) -> dict[str, object]:
        return self.pause()

    async def async_stop(self, **kwargs: Any) -> dict[str, object]:
        return self.stop(**kwargs)

    async def async_return_to_base(self, **kwargs: Any) -> dict[str, object]:
        return self.return_to_base(**kwargs)

    async def async_clean_spot(self, **kwargs: Any) -> dict[str, object]:
        return self.clean_spot(**kwargs)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> dict[str, object]:
        return self.set_fan_speed(fan_speed, **kwargs)

    async def async_send_command(
        self, command: str, params: dict | None = None, **kwargs: Any
    ) -> dict[str, object]:
        del kwargs
        return self.send_command(command, params)

    async def async_wall_follow(self) -> dict[str, object]:
        return self.wall_follow()

    async def async_single_room(self) -> dict[str, object]:
        return self.single_room()

    async def async_mop(self) -> dict[str, object]:
        return self.mop()

    async def async_remote_control(self, direction: str) -> dict[str, object]:
        return self._controller.direction(direction)

    async def async_start_kartierung(self) -> None:
        if self._session is None or self.hass is None:
            return
        if self._kartierung_task is not None and not self._kartierung_task.done():
            return
        self._session.start()
        await self.hass.async_add_executor_job(self._write_map_png)
        if await self._firmware_undock():
            self._session.undock_ticks = 0
        self._kartierung_task = self.hass.async_create_task(self._run_kartierung())

    async def _firmware_undock(self) -> bool:
        """Leave the charger with DP 25=smart, then freeze so DP 26 can take over."""
        try:
            await asyncio.wait_for(
                self.hass.async_add_executor_job(self._controller.start),
                timeout=2.5,
            )
        except Exception:
            return False
        for _ in range(16):
            await asyncio.sleep(0.5)
            try:
                status = await asyncio.wait_for(
                    self.hass.async_add_executor_job(self._controller.refresh),
                    timeout=2.0,
                )
            except Exception:
                continue
            if status is None or status.work_state is None:
                continue
            if status.work_state not in (WorkState.CHARGING, WorkState.GOING_CHARGING):
                break
        try:
            await asyncio.wait_for(
                self.hass.async_add_executor_job(self._controller.direction, "stop"),
                timeout=2.5,
            )
        except Exception:
            pass
        return True

    async def async_stop_kartierung(self) -> None:
        if self._session is not None:
            self._session.stop()
        task = self._kartierung_task
        self._kartierung_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._controller.direction("stop")
        if hasattr(self, "async_write_ha_state"):
            self.async_write_ha_state()

    def _write_map_png(self) -> None:
        if self._session is None or self.hass is None:
            return
        png = render_occupancy_png(
            self._session.grid, pose=self._session.pose, cell_px=4
        )
        path = Path(self.hass.config.path("www", "proscenic_830p_karte.png"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        self._map_rev = int(time.time() * 1000)

    async def _run_kartierung(self) -> None:
        assert self._session is not None
        status = None
        try:
            for step in range(720):
                if not self._session.running:
                    break
                dps = self._session.tick(status)
                if dps is not None:
                    try:
                        await asyncio.wait_for(
                            self.hass.async_add_executor_job(
                                self._controller.direction, dps["26"]
                            ),
                            timeout=2.5,
                        )
                    except Exception:
                        pass
                if step % 4 == 3:
                    try:
                        status = await asyncio.wait_for(
                            self.hass.async_add_executor_job(self._controller.refresh),
                            timeout=2.0,
                        )
                    except Exception:
                        status = None
                if step % 8 == 0:
                    await self.hass.async_add_executor_job(self._write_map_png)
                self.async_write_ha_state()
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            raise
        finally:
            self._session.stop()
            try:
                self._controller.direction("stop")
            except Exception:
                pass
            try:
                await self.hass.async_add_executor_job(self._write_map_png)
            except Exception:
                pass
            self.async_write_ha_state()


def build_vacuum(
    name: str,
    send_dps: SendDps,
    status_fn: Callable[[], Mapping[object, object]] | None = None,
    unique_id: str | None = None,
    session: KartierungSession | None = None,
) -> Proscenic830PVacuum:
    return Proscenic830PVacuum(
        name=name,
        controller=VacuumController(send_dps, status_fn=status_fn),
        unique_id=unique_id,
        session=session,
    )


async def async_setup_platform(
    hass: Any,
    config: Mapping[str, Any],
    async_add_entities: Callable[..., Any],
    discovery_info: Any = None,
) -> None:
    """Home Assistant yaml platform setup (vacuum: - platform: proscenic_830p)."""
    del hass, discovery_info
    host = config["host"]
    device_id = config["device_id"]
    local_key = config["local_key"]
    name = config.get("name", "Proscenic 830P")
    adapter = TuyaLanAdapter(device_id, host, local_key)

    def send_dps(dps: Mapping[str, object]) -> None:
        adapter.send_dps(dps)

    entity = build_vacuum(
        name,
        send_dps=send_dps,
        status_fn=adapter.status_dps,
        unique_id=device_id,
    )
    async_add_entities([entity], True)
    _register_extra_services()


def _register_extra_services() -> None:
    """Expose wall-follow / single-room / mop / remote-control on the HA platform."""
    try:
        from homeassistant.helpers import entity_platform  # type: ignore
        import voluptuous as vol  # type: ignore
    except ImportError:
        return
    try:
        platform = entity_platform.async_get_current_platform()
    except Exception:
        return
    platform.async_register_entity_service("wall_follow", {}, "async_wall_follow")
    platform.async_register_entity_service("single_room", {}, "async_single_room")
    platform.async_register_entity_service("mop", {}, "async_mop")
    platform.async_register_entity_service(
        "remote_control",
        {vol.Required("direction"): str},
        "async_remote_control",
    )
    platform.async_register_entity_service("kartierung", {}, "async_start_kartierung")
    platform.async_register_entity_service(
        "stop_kartierung", {}, "async_stop_kartierung"
    )
