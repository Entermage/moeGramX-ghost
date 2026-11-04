"""Same-instance TDLib client restart with topic metadata requests; JVM only, no TDLib client.

tests/forum-restart-runtime compiles the production TdApi, TdlibDataManager,
TdlibForumTopicManager.kt, ForumRequests and vkryl reference classes. Each negative
control removes exactly one fix from a copy of the production sources and must fail.
"""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "tests/forum-restart-runtime"


def gradle(*args):
    command = [str(ROOT / "gradlew"), "-p", str(PROJECT), "runChecks", "--no-daemon", "--no-watch-fs",
               "--console=plain", *args]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=os.environ.copy(), timeout=900)


class ForumRestartTest(unittest.TestCase):
    def test_restart_releases_keys_ends_waits_and_keeps_native_slots(self):
        result = gradle()
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])
        self.assertIn("checks passed", result.stdout)

    def negative(self, name, message):
        result = gradle(f"-Pnegative={name}")
        self.assertNotEqual(result.returncode, 0, result.stdout[-2000:])
        self.assertIn(message, result.stdout + result.stderr)

    def test_negative_restart_keeps_loading_keys(self):
        self.negative("restart", "same Tdlib instance must request the topic again after restart")

    def test_negative_close_drops_queued_waiters(self):
        self.negative("closed", "queued waiter must get an end state when its client closes")

    def test_negative_default_managers_end_waits_with_errors(self):
        self.negative("default-ends", "a default manager's watcher is neither ended nor fed the old client's answer")

    def test_negative_client_closed_error_cached(self):
        self.negative("cached", "client-closed error must not be cached as topic state")

    def test_negative_restart_detaches_weak_watchers_after_lock(self):
        # The coordinator's race: a weak watcher registered after contextId++ was ended by the old restart.
        self.negative("weak-restart", "new-generation weak watcher was canceled by prior restart (gap=true)")

    def test_negative_cancel_detaches_weak_watchers_after_lock(self):
        self.negative("weak-cancelled", "weak watcher registered after the cancellation was ended by it (gap=true)")

    def test_negative_answer_detaches_weak_watchers_after_lock(self):
        self.negative("weak-entry", "new-generation weak watcher got the closed client's answer (gap=true)")


if __name__ == "__main__":
    unittest.main()
