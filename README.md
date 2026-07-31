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
- [x] First agent loop wiring all three together
- [ ] Real perception ("eye"): RAM reader (Pokémon) or a small vision model
- [ ] Swappable cloud backend (e.g. Groq) for higher-quality runs

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
| `agent_loop.py` | First agent loop (10 steps, screenshots to `runs/`) |

## Roadmap

Part 2 (later, separate repo): an RL agent on the same task, followed by a
method comparison of the LLM agent vs. RL.
