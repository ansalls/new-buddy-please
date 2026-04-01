"""Buddy Reroll package."""

from .core import (
    Companion,
    Criteria,
    ORIGINAL_SALT,
    SearchResult,
    roll_companion,
    search_companion,
    search_salt,
)

__all__ = [
    "Companion",
    "Criteria",
    "ORIGINAL_SALT",
    "SearchResult",
    "roll_companion",
    "search_companion",
    "search_salt",
]

__version__ = "0.1.0"
