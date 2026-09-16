"""Occupancy map camera for live Kartierung."""

from __future__ import annotations

from .const import DOMAIN
from .map_image import render_occupancy_png

try:
    from homeassistant.components.camera import Camera  # type: ignore
except ImportError:  # pragma: no cover - HA only

    class Camera:  # type: ignore[no-redef]
        """Stand-in without Home Assistant."""

        def __init__(self) -> None:
            pass


class OccupancyMapCamera(Camera):
    _attr_should_poll = True

    def __init__(self, name: str, session, unique_id: str) -> None:
        super().__init__()
        self._attr_name = f"{name} Karte"
        self._session = session
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:floor-plan"

    def camera_image(self, width=None, height=None):
        del width, height
        return render_occupancy_png(self._session.grid, pose=self._session.pose)

    async def async_camera_image(self, width=None, height=None):
        return self.camera_image(width=width, height=height)

    @property
    def extra_state_attributes(self) -> dict:
        report = self._session.grid.report()
        return {
            "kartierung": self._session.running,
            "phase": self._session.phase,
            "reason": self._session.reason,
            "free": report.free,
            "occupied": report.occupied,
            "unknown": report.unknown,
        }


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OccupancyMapCamera(
                stored["name"],
                stored["session"],
                f"{entry.data['device_id']}_karte",
            )
        ],
        True,
    )
