"""Command-line interface for Buddy Reroll."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time
from typing import Callable, Sequence

from .core import (
    Companion,
    Criteria,
    EYES,
    HATS,
    ORIGINAL_SALT,
    RARITIES,
    SEARCH_CHARSET,
    SPECIES,
    SearchProgress,
    roll_companion,
    search_salt,
)
from .install import (
    BinaryNotFoundError,
    InstallError,
    PatchError,
    clear_cached_companion,
    find_claude_binary,
    find_claude_config,
    find_salt_in_binary,
    get_user_id,
    patch_binary,
    resolve_binary,
    revert_binary,
)

EYE_CHARS = {
    ".": "\u00b7",
    "star": "\u2726",
    "x": "\u00d7",
    "circle": "\u25c9",
    "@": "@",
    "degree": "\u00b0",
}

SPRITES = {
    "duck": ("            ", "    __      ", "  >({E} {E})   ", "   /_|     ", "  _/ /\\_    "),
    "goose": ("            ", "     __     ", " }>({E} {E})   ", "   /_|     ", " __/ /\\_    "),
    "blob": ("            ", "   .--.     ", "  ({E}  {E})   ", "  |    |   ", "   '--'    "),
    "cat": ("            ", "  /\\  /\\   ", " ( {E}  {E} )  ", "  = \\/ =   ", "   \\__/    "),
    "dragon": ("            ", "  /\\_/\\    ", " ( {E}  {E} )> ", " /|    |\\  ", "  ^^  ^^   "),
    "octopus": ("            ", "   .---.    ", "  ({E}   {E})  ", "  /||||\\   ", "  ^^^^^^^^ "),
    "owl": ("            ", "  {{   }}   ", " ( {E}  {E} )  ", "  ( \\/ )   ", "   \\||/    "),
    "penguin": ("            ", "   .--.     ", "  ({E}  {E})   ", "  /|  |\\   ", "  \\_/\\_/   "),
    "turtle": ("            ", "   _____    ", "  ({E} {E})_)  ", " /|____|   ", "  ^^  ^^   "),
    "snail": ("            ", "    @       ", "   ({E}{E})_)   ", "  /____/   ", " ~~~~~~~~  "),
    "ghost": ("            ", "   .---.    ", "  ({E}   {E})  ", "  |     |  ", "  ~^~^~^~  "),
    "axolotl": ("            ", " \\(- -)/   ", "  ({E}  {E})   ", "  /|  |\\   ", "  ^ \\/ ^   "),
    "capybara": ("            ", "   .----.   ", "  ({E}    {E}) ", "  | .--. |  ", "  \\_/  \\_/ "),
    "cactus": ("            ", "  \\| |/    ", "   |{E}{E}|    ", "  /|  |\\   ", "   |__|    "),
    "robot": ("            ", "  [====]    ", "  [{E}  {E}]   ", "  |    |   ", "  [____]   "),
    "rabbit": ("            ", "  ()  ()    ", "  ({E}  {E})   ", "  ( \\/ )   ", "   \\  /    "),
    "mushroom": ("            ", "  .----.    ", " / {E}  {E} \\  ", " |      |  ", "   |--|    "),
    "chonk": ("            ", "  .-----.   ", " ( {E}    {E} )", " |       |  ", "  '-----'  "),
}

HAT_ART = {
    "none": None,
    "crown": "    WwW     ",
    "tophat": "   _===_    ",
    "propeller": "    _|_     ",
    "halo": "    ooo     ",
    "wizard": "    /\\      ",
    "beanie": "   .==.     ",
    "tinyduck": "    >o      ",
}

RARITY_COLORS = {
    "common": "\033[97m",
    "uncommon": "\033[92m",
    "rare": "\033[94m",
    "epic": "\033[95m",
    "legendary": "\033[93m",
}
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_RESET = "\033[0m"


def configure_terminal() -> bool:
    use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    if sys.platform == "win32":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            use_color = False

    return use_color


def _color(text: str, rarity: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{RARITY_COLORS.get(rarity, '')}{text}{ANSI_RESET}"


def _bold(text: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{ANSI_BOLD}{text}{ANSI_RESET}"


def _dim(text: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{ANSI_DIM}{text}{ANSI_RESET}"


def render_sprite(companion: Companion, use_color: bool) -> list[str]:
    eye = EYE_CHARS.get(companion.eye, companion.eye)
    frames = SPRITES.get(companion.species, SPRITES["blob"])
    lines = [line.replace("{E}", eye) for line in frames]
    if companion.hat != "none" and HAT_ART.get(companion.hat):
        lines[0] = HAT_ART[companion.hat] or lines[0]
    return [_color(line, companion.rarity, use_color) for line in lines]


def stat_bar(value: int, width: int = 20) -> str:
    filled = round(value / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def format_companion(companion: Companion, use_color: bool) -> str:
    lines: list[str] = []
    tag = companion.rarity.upper()
    if companion.shiny:
        tag = f"* SHINY {tag} *"

    lines.append("")
    lines.append(_bold(_color(f"  {tag}", companion.rarity, use_color), use_color))
    lines.append("")

    for line in render_sprite(companion, use_color):
        lines.append(f"  {line}")
    lines.append("")

    eye_label = EYE_CHARS.get(companion.eye, companion.eye)
    lines.append(f"  Species: {_bold(companion.species.capitalize(), use_color):<16}Eye: {eye_label} ({companion.eye})")
    lines.append(f"  Rarity:  {_bold(companion.rarity.capitalize(), use_color):<16}Hat: {companion.hat}")
    lines.append("")

    for stat, value in companion.stats.items():
        bar = _color(stat_bar(value), companion.rarity, use_color)
        lines.append(f"  {stat:<12} {bar} {value:>3}")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Buddy Reroll - customize your Claude Code companion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s show
  %(prog)s search --species cat --rarity legendary
  %(prog)s search --rarity epic --eye star --shiny
  %(prog)s apply friend-2026-abc
  %(prog)s revert
  %(prog)s roll --user-id test-123 --salt friend-2026-401
""",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")

    subcommands = parser.add_subparsers(dest="command", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--no-color", action="store_true", help=argparse.SUPPRESS)

    show_parser = subcommands.add_parser("show", parents=[shared], help="Show your current companion")
    show_parser.add_argument("--binary", help="Path to the Claude Code binary")

    search_parser = subcommands.add_parser("search", parents=[shared], help="Search for a matching salt")
    search_parser.add_argument("--species", type=str.lower, choices=SPECIES, help="Desired species")
    search_parser.add_argument("--rarity", type=str.lower, choices=RARITIES, help="Desired rarity")
    search_parser.add_argument("--eye", type=str.lower, choices=EYES, help="Desired eye style")
    search_parser.add_argument("--hat", type=str.lower, choices=HATS, help="Desired hat")
    search_parser.add_argument("--shiny", action="store_true", help="Require shiny")
    search_parser.add_argument("--binary", help="Path to the Claude Code binary")
    search_parser.add_argument("--yes", action="store_true", help="Apply the first match without prompting")
    search_parser.add_argument(
        "--max-phase2",
        type=int,
        default=50_000_000,
        help="Maximum numeric salts to try in the extended search",
    )

    apply_parser = subcommands.add_parser("apply", parents=[shared], help="Apply a salt to the Claude Code binary")
    apply_parser.add_argument("salt", help=f"The {len(ORIGINAL_SALT)}-character salt string")
    apply_parser.add_argument("--binary", help="Path to the Claude Code binary")

    revert_parser = subcommands.add_parser("revert", parents=[shared], help="Restore the original binary from backup")
    revert_parser.add_argument("--binary", help="Path to the Claude Code binary")

    roll_parser = subcommands.add_parser("roll", parents=[shared], help="Roll a companion for testing")
    roll_parser.add_argument("--user-id", default="anon", help="User ID string")
    roll_parser.add_argument("--salt", default=ORIGINAL_SALT, help="Salt string")

    return parser


def _criteria_from_args(args: argparse.Namespace) -> Criteria:
    return Criteria(
        species=args.species,
        rarity=args.rarity,
        eye=args.eye,
        hat=args.hat,
        shiny=True if args.shiny else None,
    )


def _progress_reporter() -> Callable[[SearchProgress], None]:
    last_phase: str | None = None

    def report(progress: SearchProgress) -> None:
        nonlocal last_phase

        if progress.phase != last_phase:
            if progress.phase == "phase1":
                print(f"\n  Phase 1: searching {progress.phase_total:,} prefix-based salts...")
            else:
                print(f"\n  Phase 2: extended search (up to {progress.phase_total:,})...")
            last_phase = progress.phase
            return

        current = progress.phase_checked if progress.phase == "phase2" else progress.checked
        width = len(f"{progress.phase_total:,}")
        sys.stdout.write(f"\r  [{current:>{width},} / {progress.phase_total:,}]  {progress.rate:,.0f} salts/sec")
        sys.stdout.flush()

    return report


def _print_error(message: str) -> None:
    print(f"  Error: {message}", file=sys.stderr)


def _resolve_optional_binary(binary_arg: str | None) -> Path | None:
    if binary_arg is None:
        return find_claude_binary()
    return resolve_binary(binary_arg)


def _apply_salt(binary: Path, salt: str) -> int:
    print(f"\n  Binary: {binary}")

    location = find_salt_in_binary(binary)
    if location is None:
        _print_error("could not find the current salt in the binary")
        return 1

    print(f"  Current salt: '{location.salt}' at offset {location.offset}")

    try:
        result = patch_binary(binary, location.salt, salt)
        cache_cleared = clear_cached_companion()
    except InstallError as exc:
        _print_error(str(exc))
        return 1

    if result.created_backup:
        print(f"  Created backup: {result.backup_path}")
    print(f"  Patched {result.count} occurrence(s): '{location.salt}' -> '{salt}'")
    if result.resigned:
        print("  Re-signed binary (macOS ad-hoc)")
    if cache_cleared:
        print("  Cleared companion cache in config")
    print("\n  Done! Restart Claude Code to see your new buddy.")
    return 0


def cmd_show(args: argparse.Namespace, use_color: bool) -> int:
    config_path = find_claude_config()
    user_id = get_user_id(config_path)

    try:
        binary = _resolve_optional_binary(args.binary)
    except BinaryNotFoundError as exc:
        _print_error(str(exc))
        return 1

    current_salt = ORIGINAL_SALT
    if binary is not None:
        location = find_salt_in_binary(binary)
        if location is not None:
            current_salt = location.salt

    print(f"\n  User ID:  {user_id}")
    print(f"  Salt:     {current_salt}")
    if binary is not None:
        print(f"  Binary:   {binary}")
    elif config_path is not None:
        print(f"  Config:   {_dim(str(config_path), use_color)}")

    companion = roll_companion(user_id, current_salt)
    print(format_companion(companion, use_color))
    return 0


def cmd_search(args: argparse.Namespace, use_color: bool) -> int:
    criteria = _criteria_from_args(args)
    if criteria.is_empty():
        _print_error("no search criteria specified; use --species, --rarity, --eye, --hat, or --shiny")
        return 2

    config_path = find_claude_config()
    user_id = get_user_id(config_path)
    print(f"\n  User ID:    {user_id}")
    print(f"  Searching:  {criteria}")

    started_at = time.perf_counter()
    result = search_salt(
        user_id,
        criteria,
        max_phase2=args.max_phase2,
        progress=_progress_reporter(),
    )
    elapsed = time.perf_counter() - started_at

    if result is None:
        total = len(SEARCH_CHARSET) ** 3 + args.max_phase2
        print(f"\n  No match found after {total:,} attempts ({elapsed:.1f}s).")
        return 1

    print(f"\r  Found match after {result.attempts:,} attempts ({result.elapsed:.1f}s)       ")
    print(f"\n  Salt: {result.salt}")
    print(format_companion(result.companion, use_color))

    try:
        binary = _resolve_optional_binary(args.binary)
    except BinaryNotFoundError as exc:
        _print_error(str(exc))
        return 1

    if binary is None:
        program = Path(sys.argv[0]).name
        print("  Could not locate Claude Code binary. Apply manually with:")
        print(f"    python {program} apply {result.salt}")
        return 0

    if args.yes:
        return _apply_salt(binary, result.salt)

    if not sys.stdin.isatty():
        program = Path(sys.argv[0]).name
        print(f"  To apply later:  python {program} apply {result.salt}")
        return 0

    try:
        answer = input("  Apply this salt? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in {"y", "yes"}:
        return _apply_salt(binary, result.salt)

    program = Path(sys.argv[0]).name
    print(f"\n  To apply later:  python {program} apply {result.salt}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    if len(args.salt) != len(ORIGINAL_SALT):
        _print_error(f"salt must be exactly {len(ORIGINAL_SALT)} characters (got {len(args.salt)})")
        return 2

    try:
        binary = resolve_binary(args.binary)
    except BinaryNotFoundError as exc:
        _print_error(str(exc))
        if args.binary is None:
            print("  Use --binary <path> to specify it.", file=sys.stderr)
        return 1

    return _apply_salt(binary, args.salt)


def cmd_revert(args: argparse.Namespace) -> int:
    try:
        binary = resolve_binary(args.binary)
    except BinaryNotFoundError as exc:
        _print_error(str(exc))
        return 1

    try:
        reverted = revert_binary(binary)
    except PatchError as exc:
        _print_error(str(exc))
        return 1

    if not reverted:
        _print_error("no backup found - nothing to revert")
        return 1

    print("  Restored binary from backup.")
    print("  Reverted. Restart Claude Code to see the original buddy.")
    return 0


def cmd_roll(args: argparse.Namespace, use_color: bool) -> int:
    companion = roll_companion(args.user_id, args.salt)
    print(format_companion(companion, use_color))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    use_color = configure_terminal() and not args.no_color

    if args.command == "show":
        return cmd_show(args, use_color)
    if args.command == "search":
        return cmd_search(args, use_color)
    if args.command == "apply":
        return cmd_apply(args)
    if args.command == "revert":
        return cmd_revert(args)
    if args.command == "roll":
        return cmd_roll(args, use_color)

    parser.print_help()
    return 0
