"""Launch entry: growing snapshots plus coverage and edge paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from proscenic_830p.launch_live import run_live_file

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "kartierung_post.json"


def test_live_launch_render_has_snapshots_coverage_and_edge() -> None:
    text = run_live_file(FIXTURE)
    assert "SNAPSHOT 0 " in text
    assert "SNAPSHOT " in text
    assert "known=" in text
    assert "COVERAGE_POSE " in text
    assert "EDGE_POSE " in text
    snap_lines = [ln for ln in text.splitlines() if ln.startswith("SNAPSHOT ")]
    assert len(snap_lines) >= 2
    knowns = []
    for ln in snap_lines:
        # SNAPSHOT k known=N ...
        part = [p for p in ln.split() if p.startswith("known=")][0]
        knowns.append(int(part.split("=", 1)[1]))
    assert knowns == sorted(knowns)
    cov = [ln for ln in text.splitlines() if ln.startswith("COVERAGE_POSE ")]
    edge = [ln for ln in text.splitlines() if ln.startswith("EDGE_POSE ")]
    assert len(cov) > 1
    assert len(edge) >= 1


def test_live_launch_module_from_fresh_consumer() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "proscenic_830p.launch_live", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "SNAPSHOT 0 " in proc.stdout
    assert "COVERAGE_POSE " in proc.stdout
    assert "EDGE_POSE " in proc.stdout
