"""Supervisor relaunch rules (#6914): only on a confirmed 'down', grace after launch, storm guard."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rfl_supervisor", ROOT / "scripts" / "rfl_supervisor.py")
sup = importlib.util.module_from_spec(spec)
T0 = 1_800_000_000  # a real epoch; Windows cannot localize tiny timestamps
spec.loader.exec_module(sup)


class FakeProc(SimpleNamespace):
    def poll(self):
        return 1 if getattr(self, "dead", False) else None


def make(results, tmp_path, children_die=False):
    launches = []
    it = iter(results)

    def launch():
        launches.append(1)
        return FakeProc(pid=1000 + len(launches), dead=children_die)

    s = sup.Supervisor(probe=lambda: next(it), launch=launch, health_path=tmp_path / "h.json")
    return s, launches


def test_unknown_never_relaunches(tmp_path):
    s, launches = make(["unknown"] * 10, tmp_path)
    for i in range(10):
        s.tick(T0 + i * 30)
    assert launches == []


def test_two_downs_relaunch_once_then_grace(tmp_path):
    s, launches = make(["down"] * 6, tmp_path)
    for i in range(6):  # 0..150 s; launch at 30 s, grace to 150 s
        s.tick(T0 + i * 30)
    assert len(launches) == 1
    assert (tmp_path / "h.json").exists()


def test_storm_guard_stops_after_three(tmp_path):
    s, launches = make(["down"] * 100, tmp_path, children_die=True)
    t = T0
    for _ in range(100):
        s.tick(t)
        t += 30
    # 3000 s run: launches at most 3 inside the hour window
    assert len(launches) == 3
    assert s.state == "storm"


def test_up_resets_down_streak(tmp_path):
    s, launches = make(["down", "up", "down", "up"], tmp_path)
    for i in range(4):
        s.tick(T0 + i * 30)
    assert launches == []


def test_live_child_blocks_relaunch_past_grace(tmp_path):
    """A slow boot (child alive, port not yet bound) must never stack a second server."""
    s, launches = make(["down"] * 20, tmp_path)
    for i in range(20):  # 600 s, well past BOOT_GRACE; FakeProc never exits
        s.tick(T0 + i * 30)
    assert len(launches) == 1
    assert s.state == "launching"


def test_dead_child_is_relaunched(tmp_path):
    s, launches = make(["down"] * 12, tmp_path)
    for i in range(3):
        s.tick(T0 + i * 30)
    assert len(launches) == 1
    s.server_process.poll = lambda: 1  # child died
    for i in range(3, 12):
        s.tick(T0 + i * 30)
    assert len(launches) == 2
