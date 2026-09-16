"""Start/stop Kartierung from the device page."""

from __future__ import annotations

from .const import DOMAIN

try:
    from homeassistant.components.button import ButtonEntity  # type: ignore
except ImportError:  # pragma: no cover - HA only

    class ButtonEntity:  # type: ignore[no-redef]
        def __init__(self) -> None:
            pass


class _KartierungButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, name: str, device_id: str, action: str, label: str, icon: str) -> None:
        super().__init__()
        self._device_id = device_id
        self._action = action
        self._attr_name = label
        self._attr_unique_id = f"{device_id}_{action}"
        self._attr_icon = icon
        self._attr_device_info = {"identifiers": {(DOMAIN, device_id)}, "name": name}

    async def async_press(self) -> None:
        if self.hass is None:
            return
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

        entity_id = er.async_get(self.hass).async_get_entity_id(
            "vacuum", DOMAIN, self._device_id
        )
        if not entity_id:
            return
        await self.hass.services.async_call(
            DOMAIN,
            self._action,
            {},
            target={"entity_id": entity_id},
            blocking=False,
        )


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    device_id = entry.data["device_id"]
    name = stored["name"]
    async_add_entities(
        [
            _KartierungButton(
                name, device_id, "kartierung", "Kartierung starten", "mdi:map-plus"
            ),
            _KartierungButton(
                name,
                device_id,
                "stop_kartierung",
                "Kartierung stoppen",
                "mdi:map-marker-off",
            ),
        ]
    )
