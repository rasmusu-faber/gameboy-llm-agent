# pokemon-llm-agent

An LLM agent that autonomously plays a Game Boy game — a hands-on learning
project about building LLM agents.

The agent has three parts:

- **Eye** — reads the emulator screen (later: game state straight from RAM)
- **Hand** — presses Game Boy buttons from code
- **Brain** — a local LLM (via Ollama) that picks one action per step as JSON

The long-term goal is to play the classic **Pokémon Red** by reading the game
state from the emulator's RAM. Development currently uses **Deadeus**, a free
open-source Game Boy homebrew game, as a legal test bed.

## Status

- [x] Emulator + ROM loading (PyBoy)
- [x] Button control ("hand")
- [x] LLM decision as JSON ("brain", `llama3.2:3b` via Ollama)
- [x] First agent loop wiring all three together (placeholder eye)
- [x] Real perception ("eye"): local vision model (moondream) sees the screen
- [x] Vision agent loop: single VLM sees *and* decides (approach 1)
- [ ] Evaluate how far the tiny local VLM gets; if too weak, move to cloud vision
- [ ] Swappable cloud backend (e.g. Groq / Gemini) for higher-quality runs

## Setup

```bash
conda env create -f environment.yml
conda activate pokemon-agents
```

Install [Ollama](https://ollama.com/) separately and pull the model:

```bash
ollama pull llama3.2:3b
```

## ROM

⚠️ **ROMs are not included in this repo, and must not be.**

For development, download the free, open-source **Deadeus** ROM from the
developer's page (<https://izma.itch.io/deadeus>) and place it at
`roms/Deadeus.gb`.

The eventual Pokémon Red target requires a ROM you dump legally from a
cartridge you own. Downloading commercial ROMs from the internet is copyright
infringement and is not supported here.

## Scripts

| Script | Purpose |
|---|---|
| `test_rom.py` | Boot the ROM headless and save a screenshot |
| `test_buttons.py` | Prove button input works (before/after screenshots) |
| `test_llm.py` | Prove the local LLM returns a valid JSON action |
| `test_vision.py` | Prove a vision model can describe the actual screen |
| `agent_loop.py` | First agent loop, placeholder eye (goal + history only) |
| `agent_vision_loop.py` | Vision agent loop: one VLM sees *and* decides (approach 1) |

## Design decisions

A running log of the choices behind this project and why they were made.

- **Test bed is Deadeus, not Pokémon (yet).** The end goal is Pokémon Red, but
  its ROM is copyrighted and only legal to obtain by dumping a cartridge you
  own. Deadeus is a free, open-source Game Boy homebrew game, so it is a legal
  stand-in for building and testing the machinery.
- **Local-first with Ollama.** Free and unlimited calls for development, which
  matters because a game agent makes very many LLM calls (one per step). A
  swappable cloud backend is planned for higher-quality "real" runs.
- **Model `llama3.2:3b` for text decisions.** Chosen for RAM reasons: only
  ~5 GB was free and `llama2` (7B) needed ~8.4 GB and would not load. A modern
  3B model is also better at following the required JSON format than old 7B
  llama2 — smaller *and* more reliable here.
- **The "eye" is a vision model, not a RAM reader (for now).** A RAM reader
  needs documented memory addresses; Deadeus has none. So perception uses a
  small vision model (`moondream`, ~1.7 GB, fits in RAM). The RAM-reader
  approach is deferred to the Pokémon Red target, where the addresses are
  community-documented.
- **Approach 1 first: one VLM sees *and* decides.** Simplest wiring, RAM-
  friendly, one call per step. The alternative (moondream describes → llama3.2
  decides) is cleaner but swaps two models in tight RAM and is noticeably
  slower. If the tiny VLM proves too weak at navigation, the planned upgrade is
  a cloud vision model (e.g. Gemini Flash, free tier, multimodal) that handles
  perception and decision well without RAM limits.
- **Finding: local vision is too slow here.** Running approach 1 on this
  machine, `moondream` took *several minutes per step* (CPU inference, tight
  RAM). A game agent needs thousands of steps, so local vision is impractical
  on this hardware. The local vision code stays in the repo as a working
  reference, but perception moves to non-LLM methods below.
- **Perception without an LLM: RAM + tilemap.** Two fast, local, free signals:
  (1) a **RAM reader** finds bytes like the player's X/Y position via memory
  scanning (move, diff work RAM, keep the byte that tracks the move); (2) the
  **tilemap** exposes on-screen text. In this GB Studio game the dialog text is
  on the *window* layer and the engine streams glyphs into consecutive tiles,
  so a tile index is not a fixed character — the glyph lives in the tile's 8x8
  bitmap. Reading text therefore means matching each text tile's bitmap against
  the font once (deterministic mini-OCR, no model). The same window tilemap
  also gives a reliable screen-state signal (dialog box border tiles present or
  not), which the agent can use to know when to advance text vs. move.
- **Reaching a movable state is its own step.** Deadeus opens with a long,
  partly unskippable nightmare monologue; ~300 A-presses reliably reach the
  starting room (a movable state), verified by screenshots.
- **Robust dialog detection is deeper than expected.** A first detector keyed on
  the window-layer dialog-box tiles gave false positives: GB Studio leaves the
  box tiles in VRAM and *parks* the window off-screen (via the WX/WY position
  registers) rather than clearing it, and slides it in/out dynamically. So
  "box tiles present" and even "window enabled" are not sufficient - you must
  catch WY in the on-screen range at the right frame. Deferred as its own task;
  for now the intro is cleared with a fixed scripted A-press preamble.
- **Leaning toward Deadeus as the primary target, not just a test bed.** It is
  fully legal and open-source, which makes the project far easier to publish
  and share than anything tied to a Pokémon ROM. The RAM-reader and tilemap
  techniques are the same skills either way; Pokémon Red becomes an optional
  later target rather than the goal.
- **RAM scan works once movement is real.** With the scripted preamble in
  place, moving the character produced clear position candidates. Disambiguation
  rule that emerged: bytes that react to *both* horizontal and vertical movement
  are noise (scroll/animation/shared counters) and are discarded; axis-specific
  bytes that rise-then-return are the real coordinates.
- **Player X is at `0xC009`** (low WRAM). Live per-press tracking confirmed it:
  it steps by a fixed amount per horizontal press, returns exactly on the way
  back, and is unaffected by vertical movement. (`0xC00D`/`0xC0B7` track along
  with it - camera/copy; `0xC009` is enough.)
- **Verification matters: the first Y candidates were all noise.** The initial
  scan flagged ~21 vertical "hits" in high WRAM (0xDFxx); live tracking showed
  every one of them jittering and/or reacting to horizontal movement too. Trust
  in those would have produced a broken reader.
- **Player position found: `X=0xC009`, `Y=0xC008`.** A focused rescan of the
  low-WRAM neighborhood found Y right next to X, exactly as expected for an
  actor struct. Both step by 8 px (= 1 tile) per move, are axis-specific, and
  return cleanly. (`0xC00C/0xC00D` and `0xC0B8/0xC0B7` mirror them - camera or
  copies.) Exposed as `player_position()` / `player_tile()` in `perception.py`.
  This is the working, instant, free, local "eye" for position.
- **First navigation with a real eye works.** `agent_nav_loop.py` feeds the
  RAM-read (x, y) to the local model, which picks moves toward a target tile.
  In the first run it reached the target (Manhattan distance 32 -> 0 in 6
  moves), with one suboptimal move along the way - the small model is not
  optimal but recovers. Fully local, instant, free, no rate limits.
- **Small, verified steps.** Each capability (load ROM, press buttons, LLM
  decision, vision) was proven in isolation with its own `test_*.py` script
  before being wired into a loop.

## Roadmap

Part 2 (later, separate repo): an RL agent on the same task, followed by a
method comparison of the LLM agent vs. RL.
