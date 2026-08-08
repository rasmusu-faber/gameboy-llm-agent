# pokemon-llm-agent

![CI](https://github.com/rasmusfaber-ai/pokemon-llm-agent/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Ollama%20(local)-000000)
![Emulator](https://img.shields.io/badge/Emulator-PyBoy-5A9FD4)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

**Can a small, *local* language model play a Game Boy game — with no vision model,
seeing the world only by reading the emulator's memory?**

This is a hands-on learning project about building LLM agents from scratch. The
agent plays **Deadeus**, a free, open-source Game Boy horror game (a boy has three
in-game days and eleven possible endings). It perceives the world model-free — RAM
and the tilemap, no screenshots into a vision model — and a local LLM
(`llama3.2:3b` via Ollama) makes the judgement calls.

> **On the name.** It started as a Pokémon Red idea and pivoted to Deadeus, which
> is legal to redistribute, so the whole project can be open-sourced. The RAM- and
> tilemap-reading techniques are identical; Pokémon Red is an optional later
> target. The repo name stayed for continuity.

## The one idea worth taking away: reflexes vs. judgement

The hard-won principle the whole project is built on:

> **Deterministic code does the reflexes; the LLM only makes judgement calls.**

Pathing to a tile, sweeping a wall for a door, clicking through the intro — these
are *reflexes*. Small models do them badly (see the design log for the A/B test
where two different 3B models made the identical spatial mistake). So they live in
plain, reliable code. The LLM is spent only where judgement is actually needed:
*where* to go, *which* exit, *what* a line of dialogue means, *which* ending to aim
for. Watching the agent makes the boundary obvious — and finding it is most of the
work.

## What it can do today

- **See, without a vision model.** Player position straight from RAM
  (`0xC008/0xC009`), and on-screen text decoded from the tilemap by hashing each
  glyph's 8×8 bitmap against a ROM-derived font table — a deterministic mini-OCR,
  no model. (`src/perception.py`)
- **Reach the game on its own.** It clicks through Deadeus's long, partly
  unskippable intro by pressing A while a dialog is on screen, and confirms it has
  real control with a *reversible* movement test. (`skip_intro`)
- **Navigate a room reliably — indoors.** Deterministic tile-by-tile movement,
  plus a mini-map the agent builds from its own moves (floor where it has walked,
  walls where a move was blocked) fed into the planner's prompt. Inside the house
  this is solid, verified end-to-end; open-air navigation is not yet reliable (a
  scene-fingerprint collision outdoors — see [Status](#status--what-works-what-doesnt)).
  (`src/navigation.py`, `src/roommap.py`)
- **Remember.** A Markdown notebook (`world.md`) the agent writes as it plays:
  scenes are identified by a per-room *fingerprint* (a hash of the full background
  tilemap) and connected into a map. Writing is split — code records what it
  *measures*, the LLM records what it *interprets*. (`src/memory.py`)
- **Be watched.** `--watch` opens a live window: the upscaled game screen next to
  an overlay of what the agent perceives and decides. (`src/viewer.py`)

Current focus: getting from "explore a room" to "explore, map, read every NPC, and
pursue a goal (reach a non-violent ending)." Status and the full blow-by-blow are
in the design log.

## Status — what works, what doesn't

This is an honest work-in-progress, not a finished product. The value is the
*architecture and the investigation*, not a bot that beats the game.

**Works (verified by the test suite — 14 ROM/logic tests pass):**
- Model-free perception: player position, on-screen text (ROM-font OCR), dialog
  state, per-scene fingerprint, and the in-game day counter.
- Deterministic skills: `walk_to`, edge-sweep door-finding, `interact`, full-room
  exploration without bouncing out the first door, reverse-crossing (with a
  self-correcting map), and Yes/No **safety** (the agent never auto-confirms a
  consequential choice like sleeping).
- The intent loop end-to-end: the LLM picks `explore` / `go_to` / `interact` /
  `remember`, a deterministic skill runs it, and a persistent map notebook grows.
- A swappable LLM backend (local Ollama ↔ any OpenAI-compatible cloud).

**Partial / rough:**
- Landmark capture is noisy: a multi-tile bookshelf becomes several identical "So
  many books" landmarks; the typewriter effect truncates some captured lines.
- Returning through a known door currently re-runs the edge-sweep each time
  (correct, but not cheap).

**Not working yet / open problems:**
- **The headline finding: a 3B–8B model is the weak link.** The deterministic
  scaffolding does the heavy lifting; small models plan repetitively and reason
  poorly about space. Getting the boundary right (reflex vs. judgement) *is* the
  project — see the design log's A/B tests.
- **Outdoor navigation is broken (open issue #7).** The town is one large scene
  navigated by camera "chunks" that share a background tilemap, so the
  scene-fingerprint collides and `go_to` ping-pongs. Indoors is unaffected. A true
  per-screen invariant is still needed (a camera-based fix was tried and disproven).
- Cross-room routing over more than two rooms (map-graph BFS) isn't built yet.
- The game is **not** played to an ending; the agent explores a few indoor rooms.

## The design log is the point

**[`docs/design-log.md`](docs/design-log.md)** is a chronological record of every
decision *and every dead-end* — the local vision model that was too slow, the RAM
addresses that turned out to be noise, the LLM that walked onto the exit tile and
never stepped through. Nothing is rewritten to look clever in hindsight. If you
only read one file to understand the project, read that one.

## Quickstart

```bash
conda env create -f environment.yml
conda activate pokemon-agents
```

Install [Ollama](https://ollama.com/) separately and pull the model:

```bash
ollama pull llama3.2:3b
```

**ROM:** ⚠️ not included, and never will be. Download the free **Deadeus** ROM from
the developer (<https://izma.itch.io/deadeus>) and put it at `roms/Deadeus.gb`.

Run from the repo root:

```bash
python src/agent.py          # headless
python src/agent.py --watch  # with the live viewer
```

## Project layout

```
pokemon-llm-agent/
├── src/               # the application
│   ├── perception.py    # the "eye": position + text from RAM/tilemap; scene fingerprint
│   ├── navigation.py    # deterministic controller: walk_to / walk_direction / search_for_exit
│   ├── roommap.py       # local occupancy mini-map, built from the agent's own moves
│   ├── memory.py        # the notebook: WorldMap (scenes + connections), saved to world.md
│   ├── viewer.py        # optional live window (--watch): game screen + perception/decision overlay
│   ├── agent.py         # the loop: LLM planner + deterministic controller
│   └── deadeus_font.json # {glyph-hash: char}, all 95 printable ASCII (ROM-derived)
├── tests/             # smoke/capability tests: prove one thing each (some need the ROM)
├── exploration/       # the "workshop": one-off reverse-engineering probes (see the log)
├── docs/
│   └── design-log.md    # the chronological decision + dead-end log
├── environment.yml
└── roms/              # your own ROM goes here (git-ignored)
```

## Part 2 (later, separate)

An RL agent on the same task, then an LLM-vs-RL comparison — the recurring
"compare the methods honestly" theme of these projects.

## License

Code released under the [MIT License](LICENSE). The Deadeus ROM is **not** part of
this repository and is not covered by this license — obtain it from the developer
at <https://izma.itch.io/deadeus>.
