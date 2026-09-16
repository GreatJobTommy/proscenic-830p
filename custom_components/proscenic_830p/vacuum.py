"""Home Assistant vacuum platform for the Proscenic 830P."""

from __future__ import annotations

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
    from .const import DOMAIN  # noqa: PLC0415

    stored = hass.data[DOMAIN][entry.entry_id]
    adapter = stored["adapter"]
    entity = build_vacuum(
        stored["name"],
        send_dps=adapter.send_dps,
        status_fn=adapter.status_dps,
        unique_id=entry.data["device_id"],
        session=stored["session"],
    )
    async_add_entities([entity], True)
    from .ha_vacuum import _register_extra_services  # noqa: PLC0415

    _register_extra_services()
