import unittest

from buddyreroll.core import Criteria, ORIGINAL_SALT, roll_companion, search_companion, search_salt


class CoreTests(unittest.TestCase):
    def test_roll_companion_matches_existing_output(self) -> None:
        companion = roll_companion("test-123", ORIGINAL_SALT)

        self.assertEqual(companion.rarity, "common")
        self.assertEqual(companion.species, "octopus")
        self.assertEqual(companion.eye, ".")
        self.assertEqual(companion.hat, "none")
        self.assertFalse(companion.shiny)
        self.assertEqual(
            companion.stats,
            {
                "DEBUGGING": 1,
                "PATIENCE": 33,
                "CHAOS": 80,
                "WISDOM": 37,
                "SNARK": 30,
            },
        )

    def test_search_companion_returns_none_on_mismatch(self) -> None:
        result = search_companion("test-123", ORIGINAL_SALT, Criteria(species="cat"))
        self.assertIsNone(result)

    def test_search_salt_finds_known_phase1_match(self) -> None:
        result = search_salt("anon", Criteria(species="cat"), max_phase2=0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.salt, "friend-2026-aae")
        self.assertEqual(result.companion.species, "cat")


if __name__ == "__main__":
    unittest.main()
