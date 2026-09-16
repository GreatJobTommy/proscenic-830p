"""Proscenic 830P Home Assistant custom component (local Tuya LAN)."""

from __future__ import annotations

from .const import DOMAIN

__all__ = ["DOMAIN"]


async def async_setup(hass, config):
    del hass, config
    return True
