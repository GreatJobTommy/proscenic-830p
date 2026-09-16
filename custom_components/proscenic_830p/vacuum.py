"""Home Assistant vacuum platform for the Proscenic 830P."""

from __future__ import annotations

from .adapter import TuyaLanAdapter
from .const import CONF_LOCAL_KEY, DEFAULT_NAME
from .constants import TUYA_VERSION
from .ha_vacuum import (  # re-export for tests
    PLATFORM_SCHEMA,
    Proscenic830PVacuum,
    async_setup_platform,
    build_vacuum,
)

__all__ = [
    "PLATFORM_SCHEMA",
    "Proscenic830PVacuum",
    "async_setup_entry",
    "async_setup_platform",
    "build_vacuum",
]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    del hass
    data = entry.data
    adapter = TuyaLanAdapter(
        data["device_id"],
        data["host"],
        data[CONF_LOCAL_KEY],
        version=float(data.get("version", TUYA_VERSION)),
    )
    entity = build_vacuum(
        data.get("name", DEFAULT_NAME),
        send_dps=adapter.send_dps,
        status_fn=adapter.status_dps,
        unique_id=data["device_id"],
    )
    async_add_entities([entity], True)
