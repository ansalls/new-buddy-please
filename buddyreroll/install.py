"""Claude config and binary patching helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .core import ORIGINAL_SALT, SALT_LEN

MIN_BINARY_SIZE = 500_000
LARGE_FILE_SIZE = 1_000_000
SALT_REGEX = re.compile(rb"(friend-\d{4}-.{3}|x{5,}\d+)")
CODE_MARKERS = (b"rollRarity", b"CompanionBones", b"mulberry32", b"companion")


class InstallError(RuntimeError):
    """Base error for Claude install interactions."""


class BinaryNotFoundError(InstallError):
    """Raised when no Claude binary could be resolved."""


class SaltNotFoundError(InstallError):
    """Raised when the current salt cannot be located in a binary."""


class PatchError(InstallError):
    """Raised when patching or restoring a binary fails."""


@dataclass(frozen=True, slots=True)
class SaltLocation:
    offset: int
    salt: str


@dataclass(frozen=True, slots=True)
class PatchResult:
    count: int
    backup_path: Path
    created_backup: bool
    resigned: bool


def backup_path_for(binary_path: str | Path) -> Path:
    path = Path(binary_path).expanduser()
    return path.with_name(f"{path.name}.backup")


def find_claude_config() -> Path | None:
    candidates: list[Path] = []
    if config_dir := os.environ.get("CLAUDE_CONFIG_DIR"):
        candidates.append(Path(config_dir).expanduser() / ".config.json")

    home = Path.home()
    candidates.extend((home / ".claude" / ".config.json", home / ".claude.json"))

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", ""))
        localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates.extend(
            (
                appdata / "claude" / ".config.json",
                appdata / "Claude" / "config.json",
                localappdata / "Claude" / "config.json",
            )
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def get_user_id(config_path: str | Path | None = None) -> str:
    path = Path(config_path).expanduser() if config_path is not None else find_claude_config()
    if path is None or not path.is_file():
        return "anon"

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "anon"

    oauth_account = config.get("oauthAccount") or config.get("oauth_account") or {}
    return (
        oauth_account.get("accountUuid")
        or oauth_account.get("account_uuid")
        or config.get("userID")
        or config.get("user_id")
        or "anon"
    )


def _glob_large_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []

    matches: list[Path] = []
    try:
        for path in directory.rglob("*"):
            try:
                if path.is_file() and not path.name.endswith(".backup") and path.stat().st_size > LARGE_FILE_SIZE:
                    matches.append(path)
            except OSError:
                continue
    except OSError:
        return []
    return matches


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _binary_contains_patterns(path: Path, patterns: tuple[bytes, ...]) -> bool:
    try:
        with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            return any(mapped.find(pattern) != -1 for pattern in patterns)
    except (OSError, ValueError):
        return False


def _pick_binary(candidates: list[Path]) -> Path | None:
    deduped = _dedupe_paths(candidates)

    for candidate in deduped:
        try:
            if candidate.name.endswith(".backup"):
                continue
            if candidate.is_file() and candidate.stat().st_size >= MIN_BINARY_SIZE:
                if _binary_contains_patterns(candidate, (ORIGINAL_SALT.encode("utf-8"), b"friend-")):
                    return candidate.resolve()
        except OSError:
            continue

    for candidate in deduped:
        try:
            if candidate.name.endswith(".backup"):
                continue
            if candidate.is_file() and candidate.stat().st_size > LARGE_FILE_SIZE:
                return candidate.resolve()
        except OSError:
            continue

    return None


def find_claude_binary(explicit_path: str | Path | None = None) -> Path | None:
    if explicit_path is not None:
        path = Path(explicit_path).expanduser()
        return path.resolve() if path.is_file() else None

    candidates: list[Path] = []

    if command_path := shutil.which("claude"):
        resolved = Path(command_path).expanduser().resolve()
        candidates.append(resolved)
        candidates.extend(_glob_large_files(resolved.parent))
        if binary := _pick_binary(candidates):
            return binary

    if sys.platform == "win32":
        candidates.extend(_glob_large_files(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"))
    else:
        candidates.extend(_glob_large_files(Path.home() / ".local" / "share" / "claude"))
        candidates.extend(_glob_large_files(Path("/usr/local/lib/node_modules/@anthropic-ai")))

    version_roots = (
        Path.home() / ".local" / "share" / "claude" / "versions",
        Path(os.environ.get("LOCALAPPDATA", "")) / "claude" / "versions",
    )
    for root in version_roots:
        if not root.is_dir():
            continue
        try:
            for child in root.iterdir():
                if child.is_dir():
                    candidates.extend(_glob_large_files(child))
        except OSError:
            continue

    return _pick_binary(candidates)


def resolve_binary(binary_path: str | Path | None = None) -> Path:
    if binary_path is not None:
        path = find_claude_binary(binary_path)
        if path is None:
            raise BinaryNotFoundError(f"binary not found: {Path(binary_path).expanduser()}")
        return path

    detected = find_claude_binary()
    if detected is None:
        raise BinaryNotFoundError("could not locate Claude Code binary")
    return detected


def find_salt_in_binary(binary_path: str | Path) -> SaltLocation | None:
    path = Path(binary_path).expanduser()

    try:
        with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            original = ORIGINAL_SALT.encode("utf-8")
            index = mapped.find(original)
            if index != -1:
                return SaltLocation(offset=index, salt=ORIGINAL_SALT)

            start = 0
            while True:
                index = mapped.find(b"friend-", start)
                if index == -1:
                    break
                candidate = bytes(mapped[index : index + SALT_LEN])
                if len(candidate) == SALT_LEN and SALT_REGEX.fullmatch(candidate):
                    return SaltLocation(offset=index, salt=candidate.decode("utf-8", errors="replace"))
                start = index + 1

            for marker in CODE_MARKERS:
                position = mapped.find(marker)
                if position == -1:
                    continue
                region_start = max(0, position - 5000)
                region_end = min(len(mapped), position + 5000)
                region = bytes(mapped[region_start:region_end])
                for match in SALT_REGEX.finditer(region):
                    salt = match.group(0)
                    if len(salt) == SALT_LEN:
                        return SaltLocation(
                            offset=region_start + match.start(),
                            salt=salt.decode("utf-8", errors="replace"),
                        )

            data = bytes(mapped)
    except (OSError, ValueError):
        return None

    for match in SALT_REGEX.finditer(data):
        salt = match.group(0)
        if len(salt) == SALT_LEN:
            return SaltLocation(offset=match.start(), salt=salt.decode("utf-8", errors="replace"))
    return None


def _resign_binary(binary_path: Path) -> bool:
    if sys.platform != "darwin":
        return False

    try:
        subprocess.run(
            ["codesign", "-s", "-", "--force", str(binary_path)],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return True


def patch_binary(binary_path: str | Path, old_salt: str, new_salt: str) -> PatchResult:
    if len(new_salt) != SALT_LEN:
        raise PatchError(f"new salt must be exactly {SALT_LEN} characters (got {len(new_salt)})")

    path = Path(binary_path).expanduser()
    backup_path = backup_path_for(path)
    created_backup = False
    if not backup_path.exists():
        try:
            shutil.copy2(path, backup_path)
        except OSError as exc:
            raise PatchError(f"could not create backup: {exc}") from exc
        created_backup = True

    old_bytes = old_salt.encode("utf-8")
    new_bytes = new_salt.encode("utf-8")

    try:
        with path.open("r+b") as handle, mmap.mmap(handle.fileno(), 0) as mapped:
            offsets: list[int] = []
            start = 0
            while True:
                index = mapped.find(old_bytes, start)
                if index == -1:
                    break
                offsets.append(index)
                start = index + len(old_bytes)

            if not offsets:
                raise SaltNotFoundError(f"salt '{old_salt}' not found in binary")

            for index in offsets:
                mapped[index : index + len(old_bytes)] = new_bytes
            mapped.flush()
    except SaltNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise PatchError(f"could not patch binary: {exc}") from exc

    resigned = _resign_binary(path)
    return PatchResult(
        count=len(offsets),
        backup_path=backup_path,
        created_backup=created_backup,
        resigned=resigned,
    )


def clear_cached_companion(config_path: str | Path | None = None) -> bool:
    path = Path(config_path).expanduser() if config_path is not None else find_claude_config()
    if path is None or not path.is_file():
        return False

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    changed = False
    for key in ("companion", "companionMuted"):
        if key in config:
            del config[key]
            changed = True

    if not changed:
        return False

    try:
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise PatchError(f"could not update config: {exc}") from exc
    return True


def revert_binary(binary_path: str | Path, *, clear_cache: bool = True) -> bool:
    path = Path(binary_path).expanduser()
    backup_path = backup_path_for(path)
    if not backup_path.exists():
        return False

    try:
        shutil.copy2(backup_path, path)
    except OSError as exc:
        raise PatchError(f"could not restore backup: {exc}") from exc

    if clear_cache:
        clear_cached_companion()
    return True
