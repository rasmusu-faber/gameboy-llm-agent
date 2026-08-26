"""WorldMap.route() - shortest cross-room path (BFS), unit-tested with fake
fingerprints (no ROM needed). Groundwork for multi-hop go_to (cross-room routing):
the pure graph search over measured edges, separate from the emulator crossing.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import memory as M  # noqa: E402


def main():
    w = M.WorldMap()
    for fp in (0, 1, 2, 3, 4):                 # s0..s4 (arbitrary fake fingerprints)
        w.seen_scene(fp, (0, 0))

    # A simple chain s0 --up--> s1 --down--> s2 --left--> s3, plus a dead-end s4.
    w.connect(0, "up", 1)
    w.connect(1, "down", 2)
    w.connect(2, "left", 3)
    w.connect(1, "right", 4)

    # Multi-hop route: three rooms away, in order.
    assert w.route(0, "s3") == [("up", "s1"), ("down", "s2"), ("left", "s3")], w.route(0, "s3")

    # One hop, already there, and unknown target.
    assert w.route(0, "s1") == [("up", "s1")]
    assert w.route(0, "s0") == []              # already in the target room
    assert w.route(0, "s9") is None            # unknown room id
    assert w.route(7, "s3") is None            # unknown start scene

    # Directed edges: no reverse exists yet, so s3 -> s0 is unreachable.
    assert w.route(3, "s0") is None

    # Shortest wins: a direct shortcut s0 --right--> s3 beats the 3-hop chain.
    w.connect(0, "right", 3)
    assert w.route(0, "s3") == [("right", "s3")], w.route(0, "s3")

    # A negative fingerprint (fp_key normalisation) still routes.
    w.seen_scene(-5, (0, 0))
    w.connect(3, "down", -5)
    assert w.route(0, w.scene_id(-5)) == [("right", "s3"), ("down", "s5")], w.route(0, w.scene_id(-5))

    print("route: multi-hop, shortest-path, directed, and unreachable cases OK")
    print("PASS")


if __name__ == "__main__":
    main()
