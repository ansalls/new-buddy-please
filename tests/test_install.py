from pathlib import Path
import tempfile
import unittest

from buddyreroll.core import ORIGINAL_SALT
from buddyreroll.install import (
    backup_path_for,
    clear_cached_companion,
    find_salt_in_binary,
    get_user_id,
    patch_binary,
    revert_binary,
)


class InstallTests(unittest.TestCase):
    def test_get_user_id_reads_oauth_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".config.json"
            config_path.write_text(
                '{"oauthAccount": {"accountUuid": "abc-123"}, "companion": {"rarity": "rare"}}',
                encoding="utf-8",
            )

            self.assertEqual(get_user_id(config_path), "abc-123")

    def test_clear_cached_companion_removes_cached_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".config.json"
            config_path.write_text(
                '{"oauthAccount": {"accountUuid": "abc-123"}, "companion": {}, "companionMuted": true}',
                encoding="utf-8",
            )

            changed = clear_cached_companion(config_path)

            self.assertTrue(changed)
            content = config_path.read_text(encoding="utf-8")
            self.assertNotIn("companionMuted", content)
            self.assertNotIn('"companion": {}', content)

    def test_patch_and_revert_binary_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary_path = Path(temp_dir) / "claude.bundle"
            payload = (
                b"bundle-start"
                + ORIGINAL_SALT.encode("utf-8")
                + b"--CompanionBones--"
                + ORIGINAL_SALT.encode("utf-8")
                + b"--bundle-end"
            )
            binary_path.write_bytes(payload)

            original = find_salt_in_binary(binary_path)
            self.assertIsNotNone(original)
            assert original is not None
            self.assertEqual(original.salt, ORIGINAL_SALT)

            result = patch_binary(binary_path, ORIGINAL_SALT, "friend-2026-xyz")
            self.assertTrue(result.created_backup)
            self.assertEqual(result.count, 2)
            self.assertTrue(backup_path_for(binary_path).exists())
            self.assertIn(b"friend-2026-xyz", binary_path.read_bytes())

            patched = find_salt_in_binary(binary_path)
            self.assertIsNotNone(patched)
            assert patched is not None
            self.assertEqual(patched.salt, "friend-2026-xyz")

            self.assertTrue(revert_binary(binary_path, clear_cache=False))
            self.assertEqual(binary_path.read_bytes(), payload)

    def test_find_salt_detects_numeric_patch_near_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary_path = Path(temp_dir) / "claude.bundle"
            numeric_salt = b"xxxxxxx12345678"
            binary_path.write_bytes(b"prefix-mulberry32-suffix-" + numeric_salt + b"-end")

            location = find_salt_in_binary(binary_path)

            self.assertIsNotNone(location)
            assert location is not None
            self.assertEqual(location.salt, numeric_salt.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
