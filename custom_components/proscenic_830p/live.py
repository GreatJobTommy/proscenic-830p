"""Incremental occupancy: watch the Kartierung grid grow sample by sample."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .constants import MAPPING_BUMPER_STAMP_MM, MAPPING_RESOLUTION_MM
from .occupancy import OccupancyGrid, PoseSample


@dataclass(frozen=True)
class LiveSnapshot:
    index: int
    known: int
    free: int
    occupied: int
    unknown: int


def grid_from_fixture(data: Mapping[str, object]) -> OccupancyGrid:
    dock = data["dock"]  # type: ignore[index]
    grid = OccupancyGrid(
        resolution_mm=int(data.get("resolution_mm", MAPPING_RESOLUTION_MM)),
        origin_x_mm=float(data.get("origin_x_mm", 0)),
        origin_y_mm=float(data.get("origin_y_mm", 0)),
        width_cells=int(data.get("width_cells", 80)),
        height_cells=int(data.get("height_cells", 60)),
        bumper_stamp_radius_mm=float(
            data.get("bumper_stamp_radius_mm", MAPPING_BUMPER_STAMP_MM)
        ),
    )
    grid.mark_dock(
        float(dock["x_mm"]),  # type: ignore[index]
        float(dock["y_mm"]),  # type: ignore[index]
        float(dock.get("heading_deg", 0) or 0),  # type: ignore[union-attr]
    )
    return grid


def live_mapping_session(
    data: Mapping[str, object],
) -> tuple[OccupancyGrid, tuple[LiveSnapshot, ...]]:
    """Apply pose+bumper samples one at a time; known (free+occupied) only grows."""
    grid = grid_from_fixture(data)
    raw_samples: Sequence[object] = data["samples"]  # type: ignore[assignment]
    snapshots: list[LiveSnapshot] = []
    for index, raw in enumerate(raw_samples):
        sample = raw if isinstance(raw, PoseSample) else PoseSample.from_mapping(raw)  # type: ignore[arg-type]
        grid.observe(sample)
        report = grid.report()
        snapshots.append(
            LiveSnapshot(
                index=index,
                known=report.free + report.occupied,
                free=report.free,
                occupied=report.occupied,
                unknown=report.unknown,
            )
        )
    return grid, tuple(snapshots)
