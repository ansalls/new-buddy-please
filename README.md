# New Buddy, Please! - Claude Code `/buddy` Companion Customizer

**Reroll, preview, and patch your Claude Code buddy pet.** Pure Python, zero dependencies.

Claude Code's [`/buddy`](https://docs.anthropic.com/en/docs/claude-code) command hatches a terminal companion -- an ASCII art pet that watches your coding sessions and comments from a speech bubble. Your buddy's species, rarity, stats, eyes, hat, and shiny status are all deterministically generated from your account UUID and a hardcoded salt. This tool lets you **choose** what you get.

> Inspired by and based on [grayashh/buddy-reroll](https://github.com/grayashh/buddy-reroll) (JavaScript/Bun). This is a from-scratch Python reimplementation with no external dependencies.

---

## Features

- **Show** your current companion with full stats and ASCII art
- **Search** for a salt that produces your dream buddy (species, rarity, eyes, hat, shiny)
- **Patch** the Claude Code binary to apply the new salt
- **Revert** to the original buddy at any time via automatic backup
- **Cross-platform**: Windows, macOS, Linux
- **Zero dependencies**: just Python 3.10+

## Quick Start

```bash
# See your current buddy
python buddy_reroll.py show

# Find a legendary shiny dragon with star eyes and a wizard hat
python buddy_reroll.py search --species dragon --rarity legendary --eye star --hat wizard --shiny

# Apply the salt you found
python buddy_reroll.py apply friend-2026-hOe

# Undo and restore original buddy
python buddy_reroll.py revert
```

Or install as a package:

```bash
pip install .
buddy-reroll show
```

## Commands

| Command | Description |
| --- | --- |
| `show` | Display your current companion with ASCII art and stats |
| `search` | Brute-force search for a salt matching your desired traits |
| `apply <salt>` | Patch the Claude Code binary with a new 15-character salt |
| `revert` | Restore the binary from backup |
| `roll` | Roll a companion for any user-id/salt combo (testing) |

### Search Filters

| Flag | Options |
| --- | --- |
| `--species` | duck, goose, blob, cat, dragon, octopus, owl, penguin, turtle, snail, ghost, axolotl, capybara, cactus, robot, rabbit, mushroom, chonk |
| `--rarity` | common, uncommon, rare, epic, legendary |
| `--eye` | `.` (dot), `star`, `x`, `circle`, `@`, `degree` |
| `--hat` | none, crown, tophat, propeller, halo, wizard, beanie, tinyduck |
| `--shiny` | Flag -- require shiny variant (1% chance) |

Combine any filters. Unspecified traits are wildcards.

## How It Works

Claude Code generates your buddy deterministically:

1. **Hash**: `Bun.hash(accountUuid + salt)` using [wyhash](https://github.com/wangyi-fudan/wyhash) (Zig's `std.hash.Wyhash`)
2. **PRNG**: Lower 32 bits seed a [Mulberry32](https://gist.github.com/tommyettinger/46a874533244883189143505d203312c) generator
3. **Roll**: RNG calls determine rarity, species, eyes, hat, shiny, and stats in sequence

This tool reimplements the exact same hash and PRNG pipeline in pure Python, then brute-forces salt strings until one produces the companion you want. It patches the 15-byte salt in the Claude Code binary and clears the companion cache.

### Stats System

Each companion has 5 stats (0-100): **DEBUGGING**, **PATIENCE**, **CHAOS**, **WISDOM**, **SNARK**.

| Rarity | Probability | Stat Floor | Peak Stat | Dump Stat |
| --- | --- | --- | --- | --- |
| Common | 60% | 5 | 55-100 | 1-19 |
| Uncommon | 25% | 15 | 65-100 | 5-29 |
| Rare | 10% | 25 | 75-100 | 15-39 |
| Epic | 4% | 35 | 85-100 | 25-49 |
| Legendary | 1% | 50 | 100 | 40-54 |

Shiny is an independent 1% roll on top of rarity.

## Performance

The Phase 1 search covers 262,144 salts (prefix-based) and typically completes in **~2 seconds** at 130K+ salts/sec in pure Python. Most combinations are found in Phase 1. Phase 2 extends to millions of salts for extremely rare combos (e.g., shiny legendary of a specific species/eye/hat).

## Project Layout

```text
buddy_reroll.py          # Compatibility launcher
buddyreroll/
  core.py                # Wyhash, Mulberry32 PRNG, companion rolling, search
  install.py             # Binary/config detection, salt lookup, patching, backup
  cli.py                 # Argument parsing, display formatting, command flow
tests/                   # Unit tests
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Credits

- **[grayashh/buddy-reroll](https://github.com/grayashh/buddy-reroll)** -- The original JavaScript/Bun implementation that this project is based on. All credit for the reverse-engineering of the companion rolling algorithm, salt format, and binary patching approach goes to grayashh.
- **[Anthropic](https://anthropic.com)** -- Claude Code and the `/buddy` companion system.

## See Also

- [any-buddy](https://github.com/cpaczek/any-buddy) -- Interactive buddy reroller with macOS signing
- [cc-buddy](https://github.com/fengshao1227/cc-buddy) -- Reroller with EN/Chinese support
- [claude-buddy.vercel.app](https://claude-buddy.vercel.app/) -- Web gallery of all 18 species

## License

MIT
