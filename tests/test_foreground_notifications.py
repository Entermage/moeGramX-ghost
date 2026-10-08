"""Production foreground-service regression with Android/WorkManager doubles.

The real BaseForegroundService class, PushProcessor start method and SyncTask
schedule/cancel bodies are compiled unchanged. Device instrumentation separately
checks the installed release APK. These JVM tests do not deliver real FCM pushes.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / 'app/src/main/java/org/thunderdog/challegram/service'
SYNC = ROOT / 'app/src/main/java/org/thunderdog/challegram/sync/SyncTask.java'


def source_for(base=None, push=None, sync=None):
    base = base if base is not None else (SERVICE / 'BaseForegroundService.java').read_text()
    push = push if push is not None else block(SERVICE / 'PushProcessor.java', 'public static boolean showForegroundNotification (')
    sync = sync if sync is not None else '\n'.join(block(SYNC, signature) for signature in ('public static void cancel (', 'public static void schedule ('))
    base = base[base.index('public abstract class BaseForegroundService'):].replace('public abstract class BaseForegroundService', 'static abstract class BaseForegroundService', 1)
    kt = (SERVICE / 'ForegroundServices.kt').read_text()
    timeout = re.search(r'override fun getTaskTimeoutMillis\(\) = ([\d_]+)L', kt).group(1).replace('_', '') + 'L'
    return (ROOT / 'tests/ForegroundServiceHarness.java').read_text().replace('/* BASE_SERVICE */', base).replace('/* PUSH_START */', push).replace('/* SYNC_METHODS */', sync).replace('/* FETCH_TIMEOUT */', timeout)


def compile_harness(directory, source):
    path = Path(directory) / 'ForegroundServiceHarness.java'
    path.write_text(source)
    subprocess.run(['javac', '-d', directory, str(path)], check=True)


class ForegroundNotificationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='foreground-notification-jvm-')
        compile_harness(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name):
        subprocess.run(['java', '-ea', '-cp', self.temp.name, 'ForegroundServiceHarness', name], check=True, timeout=15)

    def test_processing_completion_before_service_start_cancels_unconfirmed_start(self): self.run_case('late-start')
    def test_interrupted_service_wait_cancels_start(self): self.run_case('interrupted')
    def test_out_of_order_and_duplicate_completion_keep_other_account_task(self): self.run_case('identity')
    def test_duplicate_start_does_not_leave_extra_task(self): self.run_case('duplicate-start')
    def test_same_push_id_on_different_accounts_is_separate(self): self.run_case('same-push-other-account')
    def test_existing_task_stop_does_not_require_system_start_permission(self): self.run_case('stop-restricted')
    def test_deadline_clears_notification_retries_and_ignores_late_completion(self): self.run_case('deadline')
    def test_staggered_task_deadlines_preserve_newer_task(self): self.run_case('staggered-deadlines')
    def test_normal_completion_cancels_watchdog(self): self.run_case('cancel-deadline')
    def test_rejected_start_releases_callback_and_allows_retry(self): self.run_case('rejected-start-callback')
    def test_callbacks_on_different_services_do_not_collide(self): self.run_case('callback-service-isolation')
    def test_retry_names_and_cancellation_match_account_scope(self): self.run_case('sync-names')

    def test_negative_control_detects_unconfirmed_start_leak(self):
        # Remove just the cancellation from the production method. No Git-history
        # dependency: CI checks the fixed commit out shallowly.
        push = block(SERVICE / 'PushProcessor.java', 'public static boolean showForegroundNotification (')
        broken = push.replace('FetchNotificationService.stopForegroundTask(context, pushId, accountId);', '', 1)
        self.assertNotEqual(push, broken)
        with tempfile.TemporaryDirectory(prefix='foreground-notification-baseline-') as directory:
            compile_harness(directory, source_for(push=broken))
            result = subprocess.run(['java', '-ea', '-cp', directory, 'ForegroundServiceHarness', 'late-start'], text=True, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('late service start left an orphan notification', result.stderr)


if __name__ == '__main__': unittest.main()
