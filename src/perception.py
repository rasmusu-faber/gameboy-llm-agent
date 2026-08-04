"""Non-LLM perception helpers built on the PyBoy emulator state.

Two model-free signals:
  - player position, read straight from work RAM;
  - on-screen text, decoded from the window tilemap by binarizing each text
    tile's 8x8 bitmap, hashing it, and looking the hash up in deadeus_font.json
    (a hash->char table derived from the ROM's ASCII-ordered font block).

Plus a small screen-state API (is a dialog box visible, what does it say).
"""

import hashlib
import json
from pathlib import Path

import numpy as np

# --- registers ---
LCDC_ADDR = 0xFF40          # bit 5 enables the window layer
LCDC_WINDOW_ENABLE = 0x20
WY_ADDR = 0xFF4A            # window Y; parked off-screen => WY >= 144
SCREEN_H = 144

# --- player position (found by memory scanning + per-press live tracking) ---
# X and Y are adjacent bytes in the actor struct and step by 8 px (= 1 tile) per
# move. (0xC00C/0xC00D and 0xC0B8/0xC0B7 mirror these - camera/copies.)
PLAYER_Y_ADDR = 0xC008
PLAYER_X_ADDR = 0xC009
TILE = 8

# --- scene identity: the full 32x32 background tilemap is a per-scene fingerprint
# (constant while scrolling inside a room, flips completely on a scene load).
BG_TILEMAP_SIZE = 32

# --- font table: md5(binarized 8x8 glyph)[:6] -> character ---
# Derived from the ROM by exploration/test_rom_font.py. Ink = bright pixel, i.e.
# (grayscale > 128), which is exactly how the table's hashes were built.
_FONT = {h: c for h, c in json.loads(
    (Path(__file__).with_name("deadeus_font.json")).read_text(encoding="utf-8")
).items() if h != "_comment"}

# Dialog text sits on these window cells (box occupies rows 0-4; text on 1-3).
# Columns skip the left/right border at 0 and 18-19.
TEXT_ROWS = (1, 2, 3)
TEXT_COLS = range(1, 18)


def player_position(pyboy):
    """Player (x, y) in raw pixel units (multiples of 8)."""
    return pyboy.memory[PLAYER_X_ADDR], pyboy.memory[PLAYER_Y_ADDR]


def player_tile(pyboy):
    """Player (x, y) in tile units."""
    x, y = player_position(pyboy)
    return x // TILE, y // TILE


def scene_fingerprint(pyboy) -> int:
    """A stable per-scene id: hash of the full 32x32 background tilemap.

    Stays constant while the player scrolls around within one room and flips
    completely on a scene load, so comparing it before/after a move detects a
    room change, and the value itself identifies a scene for map-building.
    """
    tm = pyboy.tilemap_background
    n = BG_TILEMAP_SIZE
    return hash(tuple(tm[x, y] for y in range(n) for x in range(n)))


def window_enabled(pyboy) -> bool:
    """True if the LCD window layer is currently switched on."""
    return bool(pyboy.memory[LCDC_ADDR] & LCDC_WINDOW_ENABLE)


def window_on_screen(pyboy) -> bool:
    """True if the window is scrolled into the visible area (not parked below)."""
    return pyboy.memory[WY_ADDR] < SCREEN_H


def dialog_open(pyboy) -> bool:
    """True if a dialog box is currently visible.

    GB Studio keeps the box tiles in VRAM and parks the window off-screen when
    there is no dialog, so the reliable signal is: window enabled AND scrolled
    on-screen (WY < 144), not the mere presence of box tiles.
    """
    return window_enabled(pyboy) and window_on_screen(pyboy)


def _tile_glyph_hash(pyboy, tm, x, y) -> str:
    """md5[:6] of the binarized 8x8 bitmap of the tile at window cell (x, y)."""
    try:
        tile = tm.tile(x, y)
    except (AttributeError, TypeError):
        tile = pyboy.get_tile(tm[x, y])
    nd = tile.ndarray
    if callable(nd):
        nd = nd()
    a = np.array(nd)
    if a.ndim == 3:
        a = a[..., 0]
    bits = (a > 128).astype(np.uint8)
    return hashlib.md5(bits.tobytes()).hexdigest()[:6]


def read_text(pyboy) -> str:
    """Decode the text in the window text area, model-free (unknown glyph -> '?').

    Reads whatever is in the window tilemap even if it is parked off-screen; use
    visible_dialog_text() to gate on the box actually being on screen.
    """
    tm = pyboy.tilemap_window
    lines = []
    for y in TEXT_ROWS:
        line = "".join(_FONT.get(_tile_glyph_hash(pyboy, tm, x, y), "?")
                       for x in TEXT_COLS).rstrip()
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def visible_dialog_text(pyboy) -> str:
    """The on-screen dialog text, or '' when no dialog box is visible."""
    return read_text(pyboy) if dialog_open(pyboy) else ""


def screen_state(pyboy) -> dict:
    """Coarse, LLM-free screen classification for the agent to act on."""
    dlg = dialog_open(pyboy)
    return {
        "dialog_open": dlg,
        "dialog_text": read_text(pyboy) if dlg else "",
        "window_enabled": window_enabled(pyboy),
    }
