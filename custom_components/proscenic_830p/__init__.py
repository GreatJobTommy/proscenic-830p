"""Proscenic 830P Home Assistant custom component (local Tuya LAN)."""

from __future__ import annotations

from .adapter import TuyaLanAdapter
from .const import CONF_LOCAL_KEY, DEFAULT_NAME, DOMAIN
from .constants import TUYA_VERSION
from .kartierung_session import KartierungSession

__all__ = ["DOMAIN"]

PLATFORMS = ["vacuum"]


async def async_setup(hass, config):
    del hass, config
    return True


async def async_setup_entry(hass, entry):
    data = entry.data
    adapter = TuyaLanAdapter(
        data["device_id"],
        data["host"],
        data[CONF_LOCAL_KEY],
        version=float(data.get("version", TUYA_VERSION)),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "adapter": adapter,
        "session": KartierungSession(),
        "name": data.get("name", DEFAULT_NAME),
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    stored = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if stored is not None:
        stored["session"].stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
