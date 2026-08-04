"""Map layer of memory.py, unit-tested with fake fingerprints (no ROM needed)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import memory as M  # noqa: E402

# Fake scene fingerprints (as scene_fingerprint would return: arbitrary ints,
# one intentionally negative to exercise fp_key normalisation).
BEDROOM = 0x1111_2222_3333_4444
HALLWAY = -42


def main():
    out = pathlib.Path(__file__).resolve().parents[1] / "runs" / "world_test.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    wm = M.WorldMap()
    s_bed = wm.seen_scene(BEDROOM, (56, 104))
    assert s_bed == "s0"
    # Re-seeing the same scene is idempotent (same id, no duplicate node).
    assert wm.seen_scene(BEDROOM, (56, 104)) == "s0"

    s_hall = wm.seen_scene(HALLWAY, (112, 56))
    assert s_hall == "s1"

    wm.connect(BEDROOM, "up", HALLWAY)
    wm.connect(BEDROOM, "up", HALLWAY)  # duplicate edge -> no-op
    assert len(wm._edges) == 1

    wm.save(out)
    text = out.read_text(encoding="utf-8")
    print(text)
    assert "s0 --up--> s1" in text
    assert M.fp_key(HALLWAY) in text  # negative fp normalised to hex

    # Round-trip: reload and confirm the graph is identical.
    wm2 = M.WorldMap.load(out)
    assert wm2._scenes.keys() == wm._scenes.keys()
    assert wm2._edges == wm._edges

    # Saving twice must be idempotent (block replaced, not appended).
    wm2.save(out)
    assert out.read_text(encoding="utf-8").count(M.MAP_START) == 1

    print("PASS")


if __name__ == "__main__":
    main()
