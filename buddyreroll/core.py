"""Pure companion roll and search logic."""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct
import time
from typing import Callable

ORIGINAL_SALT = "friend-2026-401"
SALT_LEN = len(ORIGINAL_SALT)

SPECIES = (
    "duck",
    "goose",
    "blob",
    "cat",
    "dragon",
    "octopus",
    "owl",
    "penguin",
    "turtle",
    "snail",
    "ghost",
    "axolotl",
    "capybara",
    "cactus",
    "robot",
    "rabbit",
    "mushroom",
    "chonk",
)

RARITIES = ("common", "uncommon", "rare", "epic", "legendary")
RARITY_WEIGHTS = {
    "common": 60,
    "uncommon": 25,
    "rare": 10,
    "epic": 4,
    "legendary": 1,
}
RARITY_TOTAL = sum(RARITY_WEIGHTS.values())
RARITY_FLOORS = {
    "common": 5,
    "uncommon": 15,
    "rare": 25,
    "epic": 35,
    "legendary": 50,
}

EYES = (".", "star", "x", "circle", "@", "degree")
HATS = ("none", "crown", "tophat", "propeller", "halo", "wizard", "beanie", "tinyduck")
STAT_NAMES = ("DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK")

SEARCH_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
SALT_PREFIX = ORIGINAL_SALT[:-3]

_WY = (
    0xA0761D6478BD642F,
    0xE7037ED1A0B428DB,
    0x8EBC6AF09C88C6E3,
    0x589965CC75374CC3,
)


@dataclass(frozen=True, slots=True)
class Companion:
    rarity: str
    species: str
    eye: str
    hat: str
    shiny: bool
    stats: dict[str, int]


@dataclass(frozen=True, slots=True)
class Criteria:
    species: str | None = None
    rarity: str | None = None
    eye: str | None = None
    hat: str | None = None
    shiny: bool | None = None

    def is_empty(self) -> bool:
        return (
            self.species is None
            and self.rarity is None
            and self.eye is None
            and self.hat is None
            and self.shiny is None
        )


@dataclass(frozen=True, slots=True)
class SearchProgress:
    phase: str
    checked: int
    phase_checked: int
    phase_total: int
    rate: float


@dataclass(frozen=True, slots=True)
class SearchResult:
    salt: str
    companion: Companion
    attempts: int
    elapsed: float


ProgressCallback = Callable[[SearchProgress], None]
_EMPTY_CRITERIA = Criteria()


def _wymum(a: int, b: int) -> tuple[int, int]:
    result = a * b
    return result & 0xFFFFFFFFFFFFFFFF, (result >> 64) & 0xFFFFFFFFFFFFFFFF


def _wymix(a: int, b: int) -> int:
    lo, hi = _wymum(a, b)
    return lo ^ hi


def _wyr8(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _wyr4(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def wyhash(data: str | bytes, seed: int = 0) -> int:
    """Compute the wyhash used by Claude Code's Bun bundle."""

    if isinstance(data, str):
        data = data.encode("utf-8")
    data = bytes(data)
    size = len(data)

    state0 = (seed ^ _wymix(seed ^ _WY[0], _WY[1])) & 0xFFFFFFFFFFFFFFFF
    state1 = state0
    state2 = state0
    a = 0
    b = 0

    if size <= 16:
        if size >= 4:
            a = (_wyr4(data, 0) << 32) | _wyr4(data, (size >> 3) << 2)
            b = (_wyr4(data, size - 4) << 32) | _wyr4(data, size - 4 - ((size >> 3) << 2))
        elif size > 0:
            a = (data[0] << 16) | (data[size >> 1] << 8) | data[size - 1]
    else:
        index = 0
        if size >= 48:
            while index + 48 < size:
                state0 = _wymix(_wyr8(data, index) ^ _WY[1], _wyr8(data, index + 8) ^ state0)
                state1 = _wymix(_wyr8(data, index + 16) ^ _WY[2], _wyr8(data, index + 24) ^ state1)
                state2 = _wymix(_wyr8(data, index + 32) ^ _WY[3], _wyr8(data, index + 40) ^ state2)
                index += 48
            state0 = (state0 ^ state1 ^ state2) & 0xFFFFFFFFFFFFFFFF

        remaining = size - index
        offset = 0
        while offset + 16 < remaining:
            state0 = _wymix(_wyr8(data, index + offset) ^ _WY[1], _wyr8(data, index + offset + 8) ^ state0)
            offset += 16
        a = _wyr8(data, size - 16)
        b = _wyr8(data, size - 8)

    a = (a ^ _WY[1]) & 0xFFFFFFFFFFFFFFFF
    b = (b ^ state0) & 0xFFFFFFFFFFFFFFFF
    a, b = _wymum(a, b)
    return _wymix((a ^ _WY[0] ^ size) & 0xFFFFFFFFFFFFFFFF, (b ^ _WY[1]) & 0xFFFFFFFFFFFFFFFF)


def companion_hash(data: str | bytes) -> int:
    return wyhash(data)


def _imul(a: int, b: int) -> int:
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


def mulberry32(seed: int) -> Callable[[], float]:
    state = [seed & 0xFFFFFFFF]

    def rng() -> float:
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        value = state[0]
        mixed = _imul(value ^ (value >> 15), 1 | value)
        mixed = (((mixed + _imul(mixed ^ (mixed >> 7), 61 | mixed)) & 0xFFFFFFFF) ^ mixed) & 0xFFFFFFFF
        return ((mixed ^ (mixed >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rng


def _roll_rarity(rng: Callable[[], float]) -> str:
    roll = rng() * RARITY_TOTAL
    for rarity in RARITIES:
        roll -= RARITY_WEIGHTS[rarity]
        if roll < 0:
            return rarity
    return "common"


def _pick(rng: Callable[[], float], options: tuple[str, ...]) -> str:
    return options[int(rng() * len(options))]


def _roll_from_seed(seed: int, criteria: Criteria) -> Companion | None:
    rng = mulberry32(seed & 0xFFFFFFFF)

    desired_rarity = criteria.rarity
    desired_species = criteria.species
    desired_eye = criteria.eye
    desired_hat = criteria.hat
    desired_shiny = criteria.shiny

    rarity = _roll_rarity(rng)
    if desired_rarity is not None and desired_rarity != rarity:
        return None

    species = _pick(rng, SPECIES)
    if desired_species is not None and desired_species != species:
        return None

    eye = _pick(rng, EYES)
    if desired_eye is not None and desired_eye != eye:
        return None

    hat = "none" if rarity == "common" else _pick(rng, HATS)
    if desired_hat is not None and desired_hat != hat:
        return None

    shiny = rng() < 0.01
    if desired_shiny is not None and desired_shiny != shiny:
        return None

    floor_value = RARITY_FLOORS[rarity]
    peak = _pick(rng, STAT_NAMES)
    dump = _pick(rng, STAT_NAMES)
    while dump == peak:
        dump = _pick(rng, STAT_NAMES)

    stats: dict[str, int] = {}
    for stat in STAT_NAMES:
        if stat == peak:
            stats[stat] = min(100, math.floor(floor_value + 50 + rng() * 30))
        elif stat == dump:
            stats[stat] = max(1, math.floor(floor_value - 10 + rng() * 15))
        else:
            stats[stat] = math.floor(floor_value + rng() * 40)

    return Companion(
        rarity=rarity,
        species=species,
        eye=eye,
        hat=hat,
        shiny=shiny,
        stats=stats,
    )


def roll_companion(user_id: str, salt: str) -> Companion:
    companion = _roll_from_seed(companion_hash(f"{user_id}{salt}"), _EMPTY_CRITERIA)
    if companion is None:
        raise RuntimeError("unreachable: roll without criteria should always produce a companion")
    return companion


def search_companion(user_id: str, salt: str, criteria: Criteria) -> Companion | None:
    return _roll_from_seed(companion_hash(f"{user_id}{salt}"), criteria)


def _report_progress(
    progress: ProgressCallback | None,
    phase: str,
    checked: int,
    phase_checked: int,
    phase_total: int,
    started_at: float,
    last_report_at: float,
    *,
    force: bool = False,
) -> float:
    if progress is None:
        return last_report_at

    now = time.perf_counter()
    if not force and now - last_report_at < 0.1:
        return last_report_at

    elapsed = max(now - started_at, 1e-9)
    progress(
        SearchProgress(
            phase=phase,
            checked=checked,
            phase_checked=phase_checked,
            phase_total=phase_total,
            rate=checked / elapsed,
        )
    )
    return now


def search_salt(
    user_id: str,
    criteria: Criteria,
    *,
    max_phase2: int = 50_000_000,
    progress: ProgressCallback | None = None,
) -> SearchResult | None:
    charset = SEARCH_CHARSET
    prefix = SALT_PREFIX
    total_phase1 = len(charset) ** 3
    checked = 0
    started_at = time.perf_counter()
    last_report_at = _report_progress(
        progress,
        "phase1",
        checked=0,
        phase_checked=0,
        phase_total=total_phase1,
        started_at=started_at,
        last_report_at=started_at,
        force=True,
    )

    for char1 in charset:
        for char2 in charset:
            base = prefix + char1 + char2
            for char3 in charset:
                salt = base + char3
                companion = search_companion(user_id, salt, criteria)
                checked += 1
                if companion is not None:
                    elapsed = time.perf_counter() - started_at
                    return SearchResult(salt=salt, companion=companion, attempts=checked, elapsed=elapsed)
                if checked % 10_000 == 0:
                    last_report_at = _report_progress(
                        progress,
                        "phase1",
                        checked=checked,
                        phase_checked=checked,
                        phase_total=total_phase1,
                        started_at=started_at,
                        last_report_at=last_report_at,
                    )

    last_report_at = _report_progress(
        progress,
        "phase2",
        checked=checked,
        phase_checked=0,
        phase_total=max_phase2,
        started_at=started_at,
        last_report_at=last_report_at,
        force=True,
    )

    for attempt in range(max_phase2):
        number = str(attempt)
        salt = "x" * (SALT_LEN - len(number)) + number
        companion = search_companion(user_id, salt, criteria)
        checked += 1
        if companion is not None:
            elapsed = time.perf_counter() - started_at
            return SearchResult(salt=salt, companion=companion, attempts=checked, elapsed=elapsed)
        if checked % 50_000 == 0:
            last_report_at = _report_progress(
                progress,
                "phase2",
                checked=checked,
                phase_checked=attempt + 1,
                phase_total=max_phase2,
                started_at=started_at,
                last_report_at=last_report_at,
            )

    return None
