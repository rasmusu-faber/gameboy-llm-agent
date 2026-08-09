"""merge_dialog(): typewriter-overlap cleanup, unit-tested with no ROM.

The cases below are the real garbled facts a 70B run wrote before the fix
(doubled words, truncated boundary words, partial re-renders). Pure string logic,
so it runs in CI without PyBoy or a model.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from navigation import merge_dialog  # noqa: E402


def main():
    # Doubled word at a page break ('I should' + 'should read ...').
    assert merge_dialog(["So many books! I should", "should read more often"]) == \
        "So many books! I should read more often"

    # Truncated boundary word re-rendered in full ('havin' -> 'having').
    assert merge_dialog(["You sounded like you were havin",
                         "you were having a bad dream"]) == \
        "You sounded like you were having a bad dream"

    # A partial render is fully contained in the next capture -> dropped.
    assert merge_dialog(["You soun", "You sounded like you were havin",
                         "you were having a bad dream"]) == \
        "You sounded like you were having a bad dream"

    # Overlap of several words ('next door came' repeated).
    assert merge_dialog(["The girl next door came", "door came knockin for you"]) == \
        "The girl next door came knockin for you"

    # In-fragment doubling ('you can you can').
    assert merge_dialog(["Using this book you can you can save your game"]) == \
        "Using this book you can save your game"

    # No false merge when fragments are genuinely distinct.
    assert merge_dialog(["Are you okay?", "Coming to eat us?"]) == \
        "Are you okay? Coming to eat us?"

    # Degenerate inputs.
    assert merge_dialog([]) == ""
    assert merge_dialog(["", "   "]) == ""
    assert merge_dialog(["A monster", "A monster?..."]) == "A monster?..."

    print("PASS")


if __name__ == "__main__":
    main()
