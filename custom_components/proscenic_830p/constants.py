"""Proscenic 830P mechanical, radio, and firmware limits."""

from __future__ import annotations

BODY_DIAMETER_MM = 330
BODY_RADIUS_MM = BODY_DIAMETER_MM // 2
BODY_HEIGHT_MM = 76
CLIMB_CONSERVATIVE_MM = 10
CLIMB_ADVERTISED_MM = 15
WIFI_BAND_GHZ = 2.4
FIRMWARE_MAIN = "1.0.3"
FIRMWARE_MCU = "1.4.3"
TUYA_PORT = 6668
TUYA_VERSION = 3.3
ROBOTBONA_PORTS = (8888, 10684)
# This unit (user-supplied device card, matched on LAN).
KNOWN_DEVICE_ID = "bf4d77d05964608b34enbm"
KNOWN_UUID = "936b5c32ba35da61"
KNOWN_SN = "SSAM17UYE023DC"
KNOWN_MAC = "68:57:2d:87:87:e9"
KNOWN_PRODUCT_KEY = "ofqlgafdltzahwlh"
DEFAULT_RESOLUTION_MM = 50
BUMPER_STAMP_RADIUS_MM = 60


def can_climb(step_mm: float) -> bool:
    """True only for steps within the conservative 10 mm climb spec."""
    return step_mm <= CLIMB_CONSERVATIVE_MM
