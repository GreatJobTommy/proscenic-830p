"""Render an occupancy grid to a PNG the HA camera entity can show."""

from __future__ import annotations

import math
import struct
import zlib

from .occupancy import Cell, OccupancyGrid, PoseSample

UNKNOWN = (42, 42, 48)
FREE = (232, 232, 228)
OCCUPIED = (28, 28, 32)
DOCK = (40, 110, 220)
ROBOT = (240, 140, 40)
HEADING = (255, 210, 80)


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def rgb_png(width: int, height: int, pixels: bytes) -> bytes:
    raw = bytearray()
    row = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * row : (y + 1) * row])
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def _put(pixels: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if not (0 <= x < width and 0 <= y < height):
        return
    index = (y * width + x) * 3
    pixels[index : index + 3] = bytes(color)


def _disk(
    pixels: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= r2:
                _put(pixels, width, height, cx + dx, cy + dy, color)


def render_occupancy_png(
    grid: OccupancyGrid,
    pose: PoseSample | None = None,
    cell_px: int = 6,
) -> bytes:
    """Top-down map: unknown dark, free light, occupied black, dock blue, robot orange."""
    width = grid.width_cells * cell_px
    height = grid.height_cells * cell_px
    pixels = bytearray(UNKNOWN * (width * height))
    dock = grid.dock_cells
    for j in range(grid.height_cells):
        py = (grid.height_cells - 1 - j) * cell_px
        for i in range(grid.width_cells):
            px = i * cell_px
            cell = grid.cell_index(i, j)
            if cell is Cell.OCCUPIED:
                color = OCCUPIED
            elif (i, j) in dock:
                color = DOCK
            elif cell is Cell.FREE:
                color = FREE
            else:
                color = UNKNOWN
            for dy in range(cell_px):
                row = (py + dy) * width * 3
                for dx in range(cell_px):
                    index = row + (px + dx) * 3
                    pixels[index : index + 3] = bytes(color)
    if pose is not None:
        i, j = grid.world_to_cell(pose.x_mm, pose.y_mm)
        cx = i * cell_px + cell_px // 2
        cy = (grid.height_cells - 1 - j) * cell_px + cell_px // 2
        _disk(pixels, width, height, cx, cy, max(3, cell_px), ROBOT)
        rad = math.radians(pose.heading_deg)
        hx = int(round(cx + math.cos(rad) * cell_px * 2))
        hy = int(round(cy - math.sin(rad) * cell_px * 2))
        _disk(pixels, width, height, hx, hy, max(2, cell_px // 2), HEADING)
    return rgb_png(width, height, bytes(pixels))
