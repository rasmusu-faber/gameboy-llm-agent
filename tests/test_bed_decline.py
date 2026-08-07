"""Goal test (issue #2): the bed auto-decline paths must NEVER sleep the player.

This matters only where sleeping is actually ENABLED (day 1 blocks the bed), so we
first advance to day 2, then check the real day byte (0xC60F) does not move when
the automatic dialog handlers run. A positive control confirms 'Yes' and shows the
day WOULD advance - so a "did not sleep" result is meaningful, not just a blocked
bed. Self-contained: day 2 is snapshotted to an in-memory buffer and reloaded
between trials (no on-disk savestate needed).
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro  # noqa: E402
from navigation import (sweep_for_crossing, advance_cutscene, walk_to, press,  # noqa: E402
                        interact, read_dialog, dismiss_dialog, dialog_open, _is_movable)

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")


def settle_after_sleep(pyboy, cap=800):
    """Advance the fade / night / wake-up until the player is movable again."""
    for _ in range(cap):
        if not _is_movable(pyboy):
            pyboy.button_press("a")
            for _ in range(4):
                pyboy.tick()
            pyboy.button_release("a")
        else:
            pyboy.tick()


def sleep_confirm(pyboy):
    walk_to(pyboy, 56, 104)
    interact(pyboy, "left")          # "Time for bed?..."
    press(pyboy, "a")                # advance text
    press(pyboy, "a")                # confirm default 'Yes'
    settle_after_sleep(pyboy)


def restore(pyboy, buf):
    buf.seek(0)
    pyboy.load_state(buf)
    for _ in range(20):
        pyboy.tick()


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)

    # Reach day 2 (the hall round-trip is what unblocks the day-1 bed), then snapshot.
    fp = P.scene_fingerprint(pyboy)
    sweep_for_crossing(pyboy, fp); advance_cutscene(pyboy)
    fp2 = P.scene_fingerprint(pyboy)
    sweep_for_crossing(pyboy, fp2); advance_cutscene(pyboy)
    sleep_confirm(pyboy)
    assert P.game_day(pyboy) == 2, f"expected day 2 after sleeping, got {P.game_day(pyboy)}"
    day2 = io.BytesIO()
    pyboy.save_state(day2)

    # Positive control: confirming 'Yes' really does advance the day here.
    restore(pyboy, day2)
    sleep_confirm(pyboy)
    assert P.game_day(pyboy) == 3, f"control: 'Yes' should sleep to day 3, got {P.game_day(pyboy)}"

    # read_dialog (skill_interact's path) must decline, not sleep.
    restore(pyboy, day2)
    walk_to(pyboy, 56, 104); press(pyboy, "left"); press(pyboy, "a")
    read_dialog(pyboy)
    assert P.game_day(pyboy) == 2 and not dialog_open(pyboy), "read_dialog slept or left a dialog open"

    # dismiss_dialog (explore-bump path) must decline, not sleep.
    restore(pyboy, day2)
    walk_to(pyboy, 56, 104); interact(pyboy, "left")
    dismiss_dialog(pyboy)
    assert P.game_day(pyboy) == 2 and not dialog_open(pyboy), "dismiss_dialog slept or left a dialog open"

    print("bed decline verified: 'Yes' -> day 3, but read_dialog & dismiss_dialog stay on day 2")
    print("PASS")
    pyboy.stop(save=False)


if __name__ == "__main__":
    main()
