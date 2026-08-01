"""Non-LLM perception helpers built on the PyBoy tilemap.

Deadeus (GB Studio) draws its dialog box with a fixed set of border tiles on
the *window* layer. Their presence is an instant, reliable signal that a dialog
is on screen - no vision model needed. This module turns that into a small
screen-state API the agent/navigation code can rely on.
"""

# Window-layer tiles that form the GB Studio dialog box border (observed in
# Deadeus). Top corners are 192/194; the box also uses 193/195/197/198/199/200.
DIALOG_TOP_LEFT = 192
DIALOG_TOP_RIGHT = 194
BLANK_TILE = 256

# LCDC register: bit 5 enables the window layer. When it is off, the window
# tilemap in VRAM still holds stale tiles (e.g. the last dialog box), so we must
# gate on this bit or we get false "dialog open" readings on the overworld.
LCDC_ADDR = 0xFF40
LCDC_WINDOW_ENABLE = 0x20

WIN_W, WIN_H = 20, 18

# Player position, found by memory scanning + per-press live tracking. X and Y
# are adjacent bytes in the actor struct and step by 8 pixels (= 1 tile) per
# move. (0xC00C/0xC00D and 0xC0B8/0xC0B7 mirror these - camera/copies.)
PLAYER_Y_ADDR = 0xC008
PLAYER_X_ADDR = 0xC009
TILE = 8


def player_position(pyboy):
    """Player (x, y) in raw pixel units (multiples of 8)."""
    return pyboy.memory[PLAYER_X_ADDR], pyboy.memory[PLAYER_Y_ADDR]


def player_tile(pyboy):
    """Player (x, y) in tile units."""
    x, y = player_position(pyboy)
    return x // TILE, y // TILE


def _window_tiles(pyboy):
    tm = pyboy.tilemap_window
    return [tm[x, y] for y in range(WIN_H) for x in range(WIN_W)]


def window_enabled(pyboy) -> bool:
    """True if the LCD window layer is currently switched on."""
    return bool(pyboy.memory[LCDC_ADDR] & LCDC_WINDOW_ENABLE)


def dialog_open(pyboy) -> bool:
    """True if a dialog box is currently drawn on the window layer.

    Requires the window layer to actually be enabled (otherwise the tilemap is
    stale), plus both top-corner border tiles present as an unambiguous box
    signature.
    """
    if not window_enabled(pyboy):
        return False
    tiles = set(_window_tiles(pyboy))
    return DIALOG_TOP_LEFT in tiles and DIALOG_TOP_RIGHT in tiles


def screen_state(pyboy) -> dict:
    """Coarse, LLM-free screen classification for the agent to act on."""
    win = _window_tiles(pyboy)
    non_blank = sum(1 for t in win if t != BLANK_TILE)
    return {
        "dialog_open": dialog_open(pyboy),
        "window_enabled": window_enabled(pyboy),
        "window_non_blank": non_blank,  # rough "is the window drawing anything"
    }
