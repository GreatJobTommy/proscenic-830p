"""Map-guided coverage and dual side-brush edge (Kanten) pass."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .constants import SIDE_BRUSH_OFFSET_DEG, SIDE_BRUSH_RADIUS_MM
from .occupancy import Cell, OccupancyGrid

_NEIGHBORS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_NEIGHBORS8 = tuple((di, dj) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj)


@dataclass(frozen=True)
class PlannedPose:
    x_mm: float
    y_mm: float
    heading_deg: float
    cell: tuple[int, int]


def side_brush_points(
    x_mm: float, y_mm: float, heading_deg: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Front-left and front-right brush tips on the 330 mm body disk."""
    rad = math.radians(heading_deg)
    left_a = rad + math.radians(SIDE_BRUSH_OFFSET_DEG)
    right_a = rad - math.radians(SIDE_BRUSH_OFFSET_DEG)
    left = (
        x_mm + SIDE_BRUSH_RADIUS_MM * math.cos(left_a),
        y_mm + SIDE_BRUSH_RADIUS_MM * math.sin(left_a),
    )
    right = (
        x_mm + SIDE_BRUSH_RADIUS_MM * math.cos(right_a),
        y_mm + SIDE_BRUSH_RADIUS_MM * math.sin(right_a),
    )
    return left, right


def brush_touches_occupied(grid: OccupancyGrid, point: tuple[float, float]) -> bool:
    """True if the brush point is on or 8-adjacent to an occupied cell."""
    i, j = grid.world_to_cell(point[0], point[1])
    if grid.cell_index(i, j) is Cell.OCCUPIED:
        return True
    for di, dj in _NEIGHBORS8:
        if grid.cell_index(i + di, j + dj) is Cell.OCCUPIED:
            return True
    return False


def _bfs_free(
    start: tuple[int, int],
    goal: tuple[int, int],
    free: set[tuple[int, int]],
) -> list[tuple[int, int]] | None:
    if start == goal:
        return [start]
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            break
        i, j = cur
        for di, dj in _NEIGHBORS4:
            nxt = (i + di, j + dj)
            if nxt in free and nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    if goal not in prev:
        return None
    path: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


def _heading_along(
    grid: OccupancyGrid, a: tuple[int, int], b: tuple[int, int]
) -> float:
    x1, y1 = grid.cell_center(*a)
    x2, y2 = grid.cell_center(*b)
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _poses_from_cells(
    grid: OccupancyGrid, cells: list[tuple[int, int]]
) -> tuple[PlannedPose, ...]:
    poses: list[PlannedPose] = []
    for n, cell in enumerate(cells):
        x_mm, y_mm = grid.cell_center(*cell)
        heading = 0.0
        if n + 1 < len(cells):
            heading = _heading_along(grid, cell, cells[n + 1])
        elif n > 0:
            heading = _heading_along(grid, cells[n - 1], cell)
        poses.append(
            PlannedPose(x_mm=x_mm, y_mm=y_mm, heading_deg=heading, cell=cell)
        )
    return tuple(poses)


def plan_coverage(grid: OccupancyGrid) -> tuple[PlannedPose, ...]:
    """Boustrophedon coverage of reachable FREE cells only (never unknown/occupied)."""
    free = set(grid.report().free_cells)
    if not free:
        return ()
    start: tuple[int, int] | None = None
    if grid.dock_pose is not None:
        dock_cell = grid.world_to_cell(grid.dock_pose[0], grid.dock_pose[1])
        if dock_cell in free:
            start = dock_cell
    if start is None:
        start = min(free)

    by_row: dict[int, list[int]] = {}
    for i, j in free:
        by_row.setdefault(j, []).append(i)
    ordered: list[tuple[int, int]] = []
    for idx, j in enumerate(sorted(by_row)):
        cols = sorted(by_row[j])
        if idx % 2:
            cols.reverse()
        ordered.extend((i, j) for i in cols)
    if start in ordered:
        k = ordered.index(start)
        ordered = ordered[k:] + ordered[:k]

    path: list[tuple[int, int]] = [start]
    visited = {start}
    for target in ordered:
        if target in visited:
            continue
        segment = _bfs_free(path[-1], target, free)
        if not segment:
            continue
        for cell in segment[1:]:
            path.append(cell)
            visited.add(cell)
    return _poses_from_cells(grid, path)


def _frontier_free_cells(grid: OccupancyGrid) -> list[tuple[int, int]]:
    free = set(grid.report().free_cells)
    out: list[tuple[int, int]] = []
    for i, j in free:
        if any(
            grid.cell_index(i + di, j + dj) is Cell.OCCUPIED for di, dj in _NEIGHBORS4
        ):
            out.append((i, j))
    return out


def _heading_for_brushes(grid: OccupancyGrid, i: int, j: int) -> float | None:
    x_mm, y_mm = grid.cell_center(i, j)
    for heading in range(0, 360, 5):
        left, right = side_brush_points(x_mm, y_mm, float(heading))
        if brush_touches_occupied(grid, left) or brush_touches_occupied(grid, right):
            return float(heading)
    return None


def plan_edge_pass(grid: OccupancyGrid) -> tuple[PlannedPose, ...]:
    """Follow occupied frontier with body on free cells and a side brush on the Rand."""
    free = set(grid.report().free_cells)
    frontier = _frontier_free_cells(grid)
    if not frontier:
        return ()
    start = frontier[0]
    if grid.dock_pose is not None:
        dock_cell = grid.world_to_cell(grid.dock_pose[0], grid.dock_pose[1])
        nearest = min(
            frontier,
            key=lambda c: abs(c[0] - dock_cell[0]) + abs(c[1] - dock_cell[1]),
        )
        start = nearest

    remaining = set(frontier)
    cells: list[tuple[int, int]] = []
    cur = start
    while remaining:
        if cur in remaining:
            remaining.remove(cur)
            cells.append(cur)
        nxt = None
        best_len: int | None = None
        for cand in remaining:
            segment = _bfs_free(cur, cand, free)
            if segment is None:
                continue
            if best_len is None or len(segment) < best_len:
                best_len = len(segment)
                nxt = cand
        if nxt is None:
            cur = min(remaining)
            continue
        segment = _bfs_free(cur, nxt, free)
        if segment:
            for cell in segment[1:]:
                if cell not in cells:
                    cells.append(cell)
                remaining.discard(cell)
        cur = nxt

    poses: list[PlannedPose] = []
    for n, cell in enumerate(cells):
        if grid.cell_index(*cell) is not Cell.FREE:
            continue
        heading = _heading_for_brushes(grid, *cell)
        if heading is None:
            if n + 1 < len(cells):
                heading = _heading_along(grid, cell, cells[n + 1])
            else:
                heading = 0.0
            x_mm, y_mm = grid.cell_center(*cell)
            left, right = side_brush_points(x_mm, y_mm, heading)
            if not (
                brush_touches_occupied(grid, left)
                or brush_touches_occupied(grid, right)
            ):
                continue
        x_mm, y_mm = grid.cell_center(*cell)
        poses.append(
            PlannedPose(x_mm=x_mm, y_mm=y_mm, heading_deg=heading, cell=cell)
        )
    return tuple(poses)
