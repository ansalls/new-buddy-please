# Buddy Reroll

Buddy Reroll is a small, dependency-free CLI for inspecting, searching, and patching the Claude Code companion salt.

## Layout

- `buddyreroll/core.py`: deterministic companion roll and brute-force search logic
- `buddyreroll/install.py`: Claude config discovery, salt lookup, backup, patch, and revert helpers
- `buddyreroll/cli.py`: argument parsing, terminal formatting, and command flow
- `buddy_reroll.py`: compatibility launcher for `python buddy_reroll.py ...`

## Commands

```bash
python buddy_reroll.py show
python buddy_reroll.py search --species cat
python buddy_reroll.py search --rarity legendary --shiny
python buddy_reroll.py apply friend-2026-abc
python buddy_reroll.py revert
python buddy_reroll.py roll --user-id test-123 --salt friend-2026-401
```

You can also install the package and use the console script:

```bash
python -m pip install .
buddy-reroll show
```

## Tests

```bash
python -m unittest discover -s tests -v
```
