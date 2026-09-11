import base64
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("ci_configure", Path(__file__).resolve().parents[1] / "scripts/ci-configure.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CiConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="moegramx-ci-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "repo"
        self.temp = Path(self.directory.name) / "runner"
        self.root.mkdir()
        self.temp.mkdir()
        self.env = {
            "ANDROID_KEYSTORE_BASE64": base64.b64encode(b"test-keystore-not-a-real-key").decode(),
            "ANDROID_KEYSTORE_PASSWORD": " secret\\value=\n",
            "ANDROID_KEY_ALIAS": "test-alias",
            "ANDROID_KEY_PASSWORD": "test-password",
            "TELEGRAM_API_ID": "123456",
            "TELEGRAM_API_HASH": "test-api-hash",
            "ANDROID_SDK_ROOT": "/tmp/test-sdk",
        }

    def test_release_configuration_and_cleanup(self):
        ci.configure(self.root, self.temp, self.env)
        signing = self.temp / "moegramx-signing"
        self.assertEqual((signing / "release.p12").read_bytes(), b"test-keystore-not-a-real-key")
        self.assertEqual(stat.S_IMODE(signing.stat().st_mode), 0o700)
        for path in (signing / "release.p12", signing / "signing.properties", self.root / "local.properties"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        local = (self.root / "local.properties").read_text()
        self.assertIn("app.experimental=false\n", local)
        self.assertIn("app.id=com.ayx.mgx\n", local)
        self.assertNotIn("test-password", local)
        ci.cleanup(self.root, self.temp)
        ci.cleanup(self.root, self.temp)
        self.assertFalse(signing.exists())
        self.assertFalse((self.root / "local.properties").exists())

    def test_java_properties_escaping(self):
        self.assertEqual(ci.property_value(" a=b:c#d!\\\n\r\t"), "\\ a\\=b\\:c\\#d\\!\\\\\\n\\r\\t")
        self.assertEqual(ci.property_value("中😀"), "\\u4e2d\\ud83d\\ude00")

    def test_missing_secret_fails_before_any_write(self):
        self.env.pop("TELEGRAM_API_HASH")
        with self.assertRaises(ValueError):
            ci.configure(self.root, self.temp, self.env)
        self.assertEqual(list(self.temp.iterdir()), [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_base64_fails_before_any_write(self):
        self.env["ANDROID_KEYSTORE_BASE64"] = "not valid base64"
        with self.assertRaises(ValueError):
            ci.configure(self.root, self.temp, self.env)
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_existing_local_config_is_preserved(self):
        local = self.root / "local.properties"
        local.write_text("user-owned-config")
        with self.assertRaises(ValueError):
            ci.configure(self.root, self.temp, self.env)
        ci.cleanup(self.root, self.temp)
        self.assertEqual(local.read_text(), "user-owned-config")

    def test_signing_symlink_is_rejected(self):
        target = self.root / "private"
        target.mkdir()
        (self.temp / "moegramx-signing").symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            ci.configure(self.root, self.temp, self.env)
        with self.assertRaises(ValueError):
            ci.cleanup(self.root, self.temp)
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
