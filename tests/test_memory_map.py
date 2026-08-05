"""Map layer of memory.py, unit-tested with fake fingerprints (no ROM needed)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

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

    # Crossing bedroom --up--> hallway from door tile (14, 8) also records the
    # reverse edge (hallway --down--> bedroom) through the spawn tile (14, 7).
    wm.note_crossing(BEDROOM, "up", HALLWAY, door_tile=(14, 8), spawn_tile=(14, 7))
    wm.note_crossing(BEDROOM, "up", HALLWAY, door_tile=(14, 8), spawn_tile=(14, 7))
    assert len(wm._edges) == 2, wm._edges                 # forward + reverse, deduped
    assert wm.door_tile(BEDROOM, "up", HALLWAY) == (14, 8)
    assert wm.door_tile(HALLWAY, "down", BEDROOM) == (14, 7)
    # The reverse edge means the fresh hallway already knows the way back.
    assert wm.exits_from(HALLWAY) == [("down", "s0")]

    # Semantic layer: labels + facts (the interpreted half, filled later).
    wm.set_label(BEDROOM, "bedroom")
    wm.add_fact(BEDROOM, "a book lies on the table")
    wm.add_fact(BEDROOM, "a book lies on the table")   # dedup
    assert wm.facts_of(BEDROOM) == ["a book lies on the table"]
    assert wm.find_by_label("Bedroom") == "s0"          # case-insensitive
    assert wm.find_by_label("church") is None            # unknown -> not a route

    # Landmark store: an interactable at a tile, keyed by tile.
    lid = wm.add_landmark(BEDROOM, (10, 6), "It   was  just a bad dream")
    assert lid == "l0"
    # First-contact descriptor wins: a later re-read does NOT overwrite it
    # (a character's unfolding dialogue must not get baked into the landmark).
    assert wm.add_landmark(BEDROOM, (10, 6), "a totally different later line") == "l0"
    lm = wm.landmarks_of(BEDROOM)
    assert lm == [{"id": "l0", "tile": (10, 6), "text": "It was just a bad dream"}], lm
    assert wm.find_landmark("l0") == {"scene": "s0", "tile": (10, 6),
                                      "text": "It was just a bad dream"}
    assert wm.find_landmark("l9") is None

    wm.save(out)
    text = out.read_text(encoding="utf-8")
    print(text)
    assert "s0 --up--> s1  door=(14, 8)" in text
    assert 'label="bedroom"' in text and "fact: a book lies on the table" in text
    assert "landmark: l0 @ (10, 6): It was just a bad dream" in text
    assert M.fp_key(HALLWAY) in text  # negative fp normalised to hex

    # Round-trip: reload and confirm the whole graph is identical.
    wm2 = M.WorldMap.load(out)
    assert wm2._scenes == wm._scenes, (wm2._scenes, wm._scenes)
    assert wm2._edges == wm._edges, (wm2._edges, wm._edges)
    assert wm2.door_tile(HALLWAY, "down", BEDROOM) == (14, 7)
    assert wm2.label_of(BEDROOM) == "bedroom"
    assert wm2.find_landmark("l0")["tile"] == (10, 6)
    # Counter restored: the next landmark after reload is l1, not l0 again.
    assert wm2.add_landmark(HALLWAY, (1, 1), "note") == "l1"

    # Saving twice must be idempotent (block replaced, not appended).
    wm2.save(out)
    assert out.read_text(encoding="utf-8").count(M.MAP_START) == 1

    print("PASS")


if __name__ == "__main__":
    main()
