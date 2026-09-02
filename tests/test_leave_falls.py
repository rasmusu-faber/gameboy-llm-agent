"""Deterministic (live navigation, no savestate fixture): the agent can cross OUT
of Urizen Falls back to the town (issue #10).

Urizen Falls is an open outdoor screen reached by the LEFT exit of the town; the
way back is RIGHT (measured raw: up/down are walls, left goes deeper, right
teleports to the town). Two ways the map can hold that edge, both must reach the
town:
  - the CORRECT edge (falls--right-->town): the fast door path presses right and crosses.
  - a WRONG guessed edge (falls--up-->town, as note_crossing would guess from a
    'down' entry): the fast path bumps the wall, then the in-place directional probe
    (_cross_by_sweep -> probe_for_crossing) finds the real right exit anyway.

Previously this drove a git-ignored savestate (runs/falls_state/screen_<falls>.state)
loaded fresh per case. That fixture turned out NOT to reproduce live physics: driving
a press from the loaded state produced ~46px position jumps and a stuck (0,0) mid-load
read that never occurred in real play (confirmed by the user hand-walking the exact
same crossing, which landed cleanly). So this test now reaches the falls by REAL
navigation from the intro (like test_explore_reaches_town), then snapshots that live
state in-memory (io.BytesIO) and restores it between the two edge-recovery trials -
same "restore a snapshot between trials" technique as test_bed_decline, but the
snapshot is produced by this run's own live play, never a stale file on disk.
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from perception import scene_fingerprint  # noqa: E402
from agent import skip_intro, explore_to_completion, skill_go_to  # noqa: E402
from navigation import step  # noqa: E402
from memory import WorldMap, fp_key  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def restore(pyboy, buf):
    buf.seek(0)
    pyboy.load_state(buf)
    for _ in range(10):
        pyboy.tick()


def _reach_town(pyboy, falls_snapshot, falls_fp, town_fp, edge_dir, door):
    """Restore the live falls snapshot, seed one falls->town edge, return whether
    go_to reaches the town."""
    restore(pyboy, falls_snapshot)
    world = WorldMap()
    world.seen_scene(town_fp, (32, 64))
    world.seen_scene(falls_fp, P.player_position(pyboy))
    town_id = world.scene_id(town_fp)
    world.connect(falls_fp, edge_dir, town_fp, door)

    _msg, cur = skill_go_to(pyboy, world, falls_fp, town_id)
    landed = world.scene_id(cur)
    return landed == town_id, _msg


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    world = WorldMap()
    cur = P.scene_fingerprint(pyboy)
    world.seen_scene(cur, P.player_position(pyboy))
    rooms, probed = {}, {}

    # bedroom (s0) -> living room (s1) -> town (s2), same path as test_explore_reaches_town
    _r, cur = explore_to_completion(pyboy, world, rooms, probed, cur)
    if world.scene_id(cur) != "s1":
        _r, cur = skill_go_to(pyboy, world, cur, "s1")
    _r, cur = explore_to_completion(pyboy, world, rooms, probed, cur)
    if world.scene_id(cur) != "s2":
        _r, cur = skill_go_to(pyboy, world, cur, "s2")
    assert world.scene_id(cur) == "s2", f"expected to reach the town, in {world.scene_id(cur)}"
    town_fp = cur

    # town (s2) -> Urizen Falls (s3): the town is an OPEN outdoor screen with SEVERAL
    # exits (up leads back to s1, per the user's confirmed topology falls is
    # specifically the town's LEFT exit) - sweep_for_crossing takes whichever edge
    # its fixed corner order reaches first (up, here), so push LEFT directly via
    # step() until a real crossing lands on a NEW scene.
    before = world.scene_count
    # The falls door sits far from the town spawn (observed at tile (1,17) across
    # several runs; spawn is (4,8)) - walk down toward its row first, THEN push left.
    for _ in range(12):
        if not step(pyboy, "down", cur).moved:
            break
    door_tile, new_fp = None, None
    for _ in range(20):
        st = step(pyboy, "left", cur)
        if st.crossed:
            door_tile, new_fp = st.from_tile, st.new_fp
            break
        if not st.moved:                    # blocked - try nudging down and retrying
            step(pyboy, "down", cur)
    assert new_fp is not None, "walking left from the town should cross into the falls"
    # No advance_cutscene here on purpose: the falls has no entry lock (confirmed),
    # and its spawn sits right at its OWN right-edge exit - advance_cutscene's
    # right-then-left mobility probe would immediately re-cross back to the town
    # (the documented "phantom third screen" gotcha), undoing the very crossing
    # just made.
    assert fp_key(new_fp) != fp_key(town_fp), "landed back on the town, not a new scene"
    world.seen_scene(new_fp, P.player_position(pyboy))
    world.note_crossing(town_fp, "left", new_fp, door_tile=door_tile,
                        spawn_tile=P.player_tile(pyboy))
    cur = new_fp
    assert world.scene_count > before, (
        f"walking left should have discovered a new scene (the falls); scenes={world.scene_count}")
    assert world.scene_id(cur) != "s2", f"expected to be AT the falls, still in {world.scene_id(cur)}"
    falls_fp = cur

    falls_spawn_tile = P.player_tile(pyboy)
    print(f"reached the falls live: {world.scene_id(falls_fp)} (fp={fp_key(falls_fp)}) "
          f"spawn_tile={falls_spawn_tile}")

    # Snapshot the live falls state in-memory - the fixture for both edge-recovery
    # trials below, produced by THIS run, never a stale file.
    falls_snapshot = io.BytesIO()
    pyboy.save_state(falls_snapshot)

    ok_right, m1 = _reach_town(pyboy, falls_snapshot, falls_fp, town_fp,
                               "right", falls_spawn_tile)   # correct edge -> fast path
    assert ok_right, f"correct-edge case did not reach the town: {m1!r}"

    # Wrong guess: the door tile is the FALLS SPAWN ITSELF (walk_to is then a no-op -
    # note this deliberately avoids a real door coordinate elsewhere on the screen:
    # walk_to() is plain, non-crossing-aware `press()`, so it can silently cross a
    # real boundary while blindly walking toward an arbitrary door guess, corrupting
    # the trial before the crossing-aware fast path/probe even runs - see the
    # design-log entry on this). 'up' is confirmed a wall here, so the fast path
    # bumps it immediately and falls through to probe_for_crossing, which must find
    # the real 'right' exit on its own.
    ok_up, m2 = _reach_town(pyboy, falls_snapshot, falls_fp, town_fp,
                            "up", falls_spawn_tile)          # wrong guess -> probe recovers
    assert ok_up, f"wrong-edge case did not reach the town: {m2!r}"

    print(f"reached town both ways (correct edge: {m1!r}; wrong-guess recovery: {m2!r})")
    print("PASS")
    pyboy.stop(save=False)


if __name__ == "__main__":
    main()
