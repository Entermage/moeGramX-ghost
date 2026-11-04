"""Negative controls for the external-share boundary checks in tests/external-share-android.

Each run compiles ExternalShareUtils with one check removed and must fail on the real
android.net.Uri. Nothing is shared, read from a provider, or sent.
"""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "tests/external-share-android"


def gradle(*args):
    return subprocess.run([str(ROOT / "gradlew"), "-p", str(PROJECT), "runChecks", "--no-daemon", "--no-watch-fs",
                           "--console=plain", *args], cwd=ROOT, capture_output=True, text=True, env=os.environ.copy(),
                          timeout=900)


class ExternalShareBoundaryTest(unittest.TestCase):
    def negative(self, name, message):
        result = gradle(f"-Pnegative={name}")
        self.assertNotEqual(result.returncode, 0, result.stdout[-2000:])
        self.assertIn(message, result.stdout + result.stderr)

    def test_negative_own_provider_accepted(self):
        self.negative("own-provider", "this app's own provider must not be read for an outside app")

    def test_negative_app_specific_storage_accepted(self):
        self.negative("app-specific", "a file URI into this app's private storage is refused")

    def test_negative_device_protected_storage_accepted(self):
        self.negative("device-protected", "a file URI into this app's device-protected storage is refused")

    def test_negative_user_id_prefixed_own_provider_accepted(self):
        # Without stripping "<userId>@", content://0@<authority>/ reaches this app's provider unchecked.
        self.negative("user-id", "this app's own provider must not be read for an outside app: content://0@com.ayx.mgx.provider/logs/tdlib_log.txt")

    def test_positive_boundary_checks(self):
        result = gradle()
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])
        self.assertIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
