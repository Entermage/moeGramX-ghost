"""Run production TDLib notification methods with deterministic runtime doubles.

The real add/delay/update-coalescing methods are compiled, not reimplemented.
The actor scheduler, Telegram objects and storage are doubles; real FCM and
Android notification listener behavior still need a target-device test.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'tdlib/source/td/td/telegram/NotificationManager.cpp'


class NotificationHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='notification-patched-source-')
        cls.patched = Path(cls.temp.name)
        patch = ROOT / 'patches/tdlib-ghost-mode.patch'
        native_root = ROOT / 'tdlib/source/td'
        for name in re.findall(r'^--- a/(.+)$', patch.read_text(), re.M):
            target = cls.patched / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output([
                'git', '-C', str(native_root), 'show', 'HEAD:' + name
            ]))
        subprocess.run(['git', 'apply', str(patch)], cwd=cls.patched, check=True)
        cls.native = cls.patched / 'td/telegram/NotificationManager.cpp'

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_production_notification_handoff_and_update_batching(self):
        methods = '\n\n'.join(block(self.native, signature) for signature in (
            'int32 NotificationManager::get_notification_delay_ms(',
            'void NotificationManager::add_notification(',
            'void NotificationManager::flush_pending_updates(',
            'void NotificationManager::force_flush_pending_updates(',
        ))
        harness = (ROOT / 'tests/notification_handoff_harness.cpp').read_text()
        self.assertEqual(harness.count('/* PRODUCTION_METHODS */'), 1)
        with tempfile.TemporaryDirectory(prefix='notification-handoff-') as tmp:
            source = Path(tmp) / 'handoff.cpp'
            executable = Path(tmp) / 'handoff'
            source.write_text(harness.replace('/* PRODUCTION_METHODS */', methods))
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Wno-unused-parameter',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            '-g', '-o', str(executable), str(source)], check=True)
            subprocess.run([str(executable)], check=True)

    def test_patch_applies_and_preserves_explicit_removal_paths(self):
        """Check the deliverable patch, including pre-existing Ghost modifications."""
        native_root = NATIVE.parents[2]
        patch = ROOT / 'patches/tdlib-ghost-mode.patch'
        subprocess.run(['git', '-C', str(self.patched), 'apply', '--reverse', '--check',
                        str(patch)], check=True)
        original = subprocess.check_output([
            'git', '-C', str(native_root), 'show', 'HEAD:td/telegram/NotificationManager.cpp'
        ]).decode()
        with tempfile.TemporaryDirectory(prefix='notification-removal-baseline-') as tmp:
            original_file = Path(tmp) / 'NotificationManager.cpp'
            original_file.write_text(original)
            for signature in ('void NotificationManager::remove_notification(',
                              'void NotificationManager::remove_notification_group(',
                              'void NotificationManager::remove_temporary_notification_by_object_id('):
                self.assertEqual(block(self.native, signature), block(original_file, signature))


if __name__ == '__main__':
    unittest.main()
