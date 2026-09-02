"""Goal test: the auto-decline paths must NEVER save the game at the bedroom book.

The save book opens a 'Save Game?' / 'Cancel' menu - NOT Yes/No. A detector that
only knew Yes/No fell through to a plain-text A-press, which confirmed the default
'Save Game?' and saved on every touch (the round-12 save loop). This guards the
generalized two-option-menu handling: a positive control confirms that pressing A
really DOES save (so 'saved' text is detectable), then the read_dialog and
dismiss_dialog paths must reach the same book and leave WITHOUT saving.

Self-contained: snapshots the movable bedroom state and reloads it between trials.
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pyboy import PyBoy  # noqa: E402

import perception as P  # noqa: E402
from agent import skip_intro, _dir_to  # noqa: E402
from navigation import (walk_to, press, read_dialog, dismiss_dialog,  # noqa: E402
                        dialog_open, visible_dialog_text)

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = str(ROOT / "roms" / "Deadeus.gb")

BOOK = (13, 13)   # the save-book tile in the bedroom


def restore(pyboy, buf):
    buf.seek(0)
    pyboy.load_state(buf)
    for _ in range(20):
        pyboy.tick()


def trigger_book(pyboy):
    """Walk beside the save book, face it, and press A to open its dialog."""
    walk_to(pyboy, BOOK[0] * 8, BOOK[1] * 8)
    face = _dir_to(P.player_tile(pyboy), BOOK)
    if face:
        press(pyboy, face)
    press(pyboy, "a")


def confirm_save(pyboy, max_presses=12) -> str:
    """The OLD buggy behavior on purpose: blow through with A, confirming the
    default 'Save Game?'. Returns all text seen (should include 'Game saved!')."""
    seen = []
    for _ in range(max_presses):
        txt = visible_dialog_text(pyboy)
        if txt:
            seen.append(txt)
        press(pyboy, "a")
    return " ".join(seen)


def main():
    pyboy = PyBoy(ROM, window="null")
    for _ in range(600):
        pyboy.tick()
    skip_intro(pyboy)
    movable = io.BytesIO()
    pyboy.save_state(movable)

    # Positive control: forcing A really saves here (so 'saved' IS detectable).
    trigger_book(pyboy)
    control = confirm_save(pyboy)
    assert "saved" in control.lower(), (
        f"control: pressing A should save, but no 'saved' text seen: {control!r}")

    # read_dialog (skill_interact's path) must decline the menu, not save.
    restore(pyboy, movable)
    trigger_book(pyboy)
    heard = read_dialog(pyboy)
    assert "saved" not in heard.lower() and not dialog_open(pyboy), (
        f"read_dialog saved the game or left a dialog open: {heard!r}")

    # dismiss_dialog (explore-bump path) must decline the menu, not save.
    restore(pyboy, movable)
    trigger_book(pyboy)
    dismiss_dialog(pyboy)
    leftover = visible_dialog_text(pyboy)
    assert "saved" not in leftover.lower() and not dialog_open(pyboy), (
        f"dismiss_dialog saved the game or left a dialog open: {leftover!r}")

    print("save-book decline verified: forcing A saves, but read_dialog & "
          "dismiss_dialog leave without saving")
    print("PASS")
    pyboy.stop(save=False)


if __name__ == "__main__":
    main()
