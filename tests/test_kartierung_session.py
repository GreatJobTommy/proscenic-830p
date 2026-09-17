from proscenic_830p.kartierung_session import LIVE_TURN_TICKS, KartierungSession
from proscenic_830p.map_image import render_occupancy_png
from proscenic_830p.occupancy import Cell, PoseSample
from proscenic_830p.protocol import Fault, VacuumStatus, WorkState


def _status(*, hit: bool = False) -> VacuumStatus:
    return VacuumStatus(
        battery=100,
        work_state=WorkState.REMOTE,
        fan=None,
        faults=Fault.COLLISION_SENSOR if hit else Fault.NO_ERROR,
        mop_equipped=False,
        cleaned_area=None,
        clean_time_min=None,
        raw={},
    )


def test_session_start_marks_dock_and_png_is_png() -> None:
    session = KartierungSession()
    session.start()
    assert session.running is True
    assert session.grid.dock_pose is not None
    assert session.grid.report().dock_cells
    png = render_occupancy_png(session.grid, pose=session.pose)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 200


def test_first_tick_without_bumper_drives_forward() -> None:
    session = KartierungSession(undock_ticks=0)
    session.start()
    dps = session.tick(_status(hit=False), dt_s=0.2)
    assert dps == {"26": "forward"}
    assert session.phase == "explore"


def test_unchanged_direction_is_not_resent() -> None:
    session = KartierungSession(undock_ticks=0)
    session.start()
    assert session.tick(_status(hit=False), dt_s=0.2) == {"26": "forward"}
    assert session.tick(_status(hit=False), dt_s=0.2) is None
    assert session.tick(_status(hit=False), dt_s=0.2) is None


def test_undock_ignores_dock_bumper() -> None:
    session = KartierungSession(undock_ticks=3)
    session.start()
    first = session.tick(_status(hit=True), dt_s=0.2)
    assert first == {"26": "forward"}
    assert session.reason == "undock"
    assert session.tick(_status(hit=True), dt_s=0.2) is None
    assert session.tick(_status(hit=True), dt_s=0.2) is None
    assert session.grid.report().occupied == 0


def test_bumper_hit_backs_off_and_stamps_occupied() -> None:
    session = KartierungSession(undock_ticks=0, live_drive=False)
    session.start()
    session.tick(_status(hit=False), dt_s=0.2)
    dps = session.tick(_status(hit=True), dt_s=0.2)
    assert dps == {"26": "backward"}
    assert session.grid.report().occupied > 0
    assert session.phase == "backoff"


def test_sticky_bumper_does_not_retrigger_while_backing() -> None:
    session = KartierungSession(undock_ticks=0, live_drive=False)
    session.start()
    session.tick(_status(hit=False), dt_s=0.2)
    session.tick(_status(hit=True), dt_s=0.2)
    dps = session.tick(_status(hit=True), dt_s=0.2)
    assert dps is None
    assert session.phase == "backoff"


def test_live_drive_never_sends_backward() -> None:
    session = KartierungSession(undock_ticks=0, live_drive=True)
    session.start()
    assert session.tick(_status(hit=False), dt_s=0.2) == {"26": "forward"}
    dps = session.tick(_status(hit=True), dt_s=0.2)
    assert dps == {"26": "turnleft"}
    assert session.tick(_status(hit=True), dt_s=0.2) is None
    sent = {session.last_direction}
    assert "backward" not in sent
    assert session.grid.report().occupied > 0


def _assert_overlay_only(dps: dict[str, str] | None) -> None:
    if dps is None:
        return
    assert list(dps.keys()) == ["26"]
    assert "25" not in dps
    assert "smart" not in dps.values()
    assert dps["26"] != "backward"


def test_live_drive_holds_forward_then_turns_never_smart() -> None:
    session = KartierungSession(undock_ticks=0, live_drive=True)
    session.start()
    first = session.tick(_status(hit=False), dt_s=0.2)
    assert first == {"26": "forward"}
    _assert_overlay_only(first)
    assert session.tick(_status(hit=False), dt_s=0.2) is None
    assert session.tick(_status(hit=False), dt_s=0.2) is None
    hit_cmd = session.tick(_status(hit=True), dt_s=0.2)
    assert hit_cmd == {"26": "turnleft"}
    _assert_overlay_only(hit_cmd)
    sticky = [session.tick(_status(hit=True), dt_s=0.2) for _ in range(12)]
    emitted = [cmd for cmd in sticky if cmd is not None]
    for cmd in emitted:
        _assert_overlay_only(cmd)
    dirs = [cmd["26"] for cmd in emitted]
    assert "backward" not in dirs
    for prev, nxt in zip(dirs, dirs[1:]):
        assert {prev, nxt} != {"forward", "backward"}
    assert {"25": "smart"} not in sticky


def test_live_drive_turn_then_forward_after_hit() -> None:
    session = KartierungSession(undock_ticks=0, live_drive=True)
    session.start()
    session.tick(_status(hit=False), dt_s=0.2)
    assert session.tick(_status(hit=True), dt_s=0.2) == {"26": "turnleft"}
    held = [session.tick(_status(hit=False), dt_s=0.2) for _ in range(LIVE_TURN_TICKS - 1)]
    assert all(cmd is None for cmd in held)
    resume = session.tick(_status(hit=False), dt_s=0.2)
    assert resume == {"26": "forward"}
    _assert_overlay_only(resume)


def test_live_drive_occupancy_grows_free_sticky_occupied_unknown_stays() -> None:
    session = KartierungSession(undock_ticks=0, live_drive=True)
    session.start()
    free_before = session.grid.report().free
    session.tick(_status(hit=False), dt_s=0.2)
    session.tick(_status(hit=False), dt_s=0.2)
    session.tick(_status(hit=False), dt_s=0.2)
    free_mid = session.grid.report().free
    assert free_mid >= free_before
    session.tick(_status(hit=True), dt_s=0.2)
    report_hit = session.grid.report()
    assert report_hit.occupied > 0
    occupied_xy = report_hit.occupied_cells[0]
    ox, oy = session.grid.cell_center(*occupied_xy)
    assert session.grid.cell_at(ox, oy) is Cell.OCCUPIED
    session.grid.observe(PoseSample(x_mm=ox, y_mm=oy, heading_deg=0.0, bumper=False))
    assert session.grid.cell_at(ox, oy) is Cell.OCCUPIED
    far = session.grid.cell_at(session.grid.origin_x_mm + 12.0, session.grid.origin_y_mm + 12.0)
    assert far is Cell.UNKNOWN
    session.tick(_status(hit=False), dt_s=0.2)
    cmds = []
    session2 = KartierungSession(undock_ticks=0, live_drive=True)
    session2.start()
    cmds.append(session2.tick(_status(hit=False), dt_s=0.2))
    cmds.append(session2.tick(_status(hit=True), dt_s=0.2))
    for _ in range(LIVE_TURN_TICKS):
        cmds.append(session2.tick(_status(hit=False), dt_s=0.2))
    emitted = [c["26"] for c in cmds if c is not None]
    assert emitted[0] == "forward"
    assert "turnleft" in emitted
    assert "backward" not in emitted
    assert emitted[-1] == "forward"
    assert not any(c and "25" in c for c in cmds)


def test_stop_halts_session() -> None:
    session = KartierungSession()
    session.start()
    session.stop()
    assert session.running is False
    assert session.tick(_status(), dt_s=0.2) is None
