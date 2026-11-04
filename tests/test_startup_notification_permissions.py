"""Production startup permission coordinator and MainController lifecycle regression.

Android permission delivery is doubled; real-device denial/resume verification
is still required. The test never grants or changes any device permission.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY = ROOT / "app/src/main/java/org/thunderdog/challegram/BaseActivity.java"
MAIN = ROOT / "app/src/main/java/org/thunderdog/challegram/ui/MainController.java"


def source_for(broken=False):
    activity = ACTIVITY.read_text()
    fields = activity[activity.index("  private final ArrayList<Integer> startupNotificationAccounts"):activity.index("  public void requestStartupPostNotifications (")]
    methods = "\n".join(block(ACTIVITY, signature) for signature in (
        "public void requestStartupPostNotifications (", "private void finishStartupPostNotifications (",
    ))
    if broken:
        methods = methods.replace("if (startupNotificationAccounts.contains(accountId))", "if (false)").replace("if (startupNotificationsRequested)", "if (false)")
    main = "\n".join(block(MAIN, signature) for signature in (
        "private void showAnnoyingAlertsForCompliance (", "public void onActivityResume (", "public void onFocus (",
    ))
    return (ROOT / "tests/StartupNotificationPermissionHarness.java").read_text().replace("/* ACTIVITY_FIELDS */", fields).replace("/* ACTIVITY_METHODS */", methods).replace("/* MAIN_METHODS */", main)


def compile_harness(directory, source):
    path = Path(directory) / "StartupNotificationPermissionHarness.java"
    path.write_text(source)
    subprocess.run(["javac", "-d", directory, str(path)], check=True)


class StartupNotificationPermissionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moex-startup-permission-")
        compile_harness(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, name):
        subprocess.run(["java", "-cp", self.temp.name, "StartupNotificationPermissionHarness", name], check=True, timeout=15)

    def test_denial_and_forty_resume_events_do_not_reprompt(self): self.run_case("denial-loop")
    def test_both_main_controllers_share_one_account_startup(self): self.run_case("two-panes")
    def test_accounts_wait_and_explicit_settings_retry_remains_available(self): self.run_case("accounts")
    def test_existing_grant_and_pre_android13_continue_without_prompt(self): self.run_case("granted-legacy")
    def test_immediate_denial_new_activity_and_destroyed_controller(self): self.run_case("lifecycle")

    def test_negative_control_detects_denied_permission_resume_loop(self):
        with tempfile.TemporaryDirectory(prefix="moex-startup-permission-broken-") as directory:
            compile_harness(directory, source_for(broken=True))
            result = subprocess.run(["java", "-cp", directory, "StartupNotificationPermissionHarness", "denial-loop"], text=True, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("resume reopened denied notification permission", result.stderr)


if __name__ == "__main__":
    unittest.main()
