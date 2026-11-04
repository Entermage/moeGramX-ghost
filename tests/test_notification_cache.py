"""Run real notification cache methods on the JVM with Android/TDLib doubles.

The Group.updateGroup and Helper.updateGroup/onGroupChanged bodies are extracted
unchanged from production. Android posting and TDLib delivery are doubles; these
checks do not replace FCM, notification shade, or OEM background device tests.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/src/main/java/org/thunderdog/challegram/telegram"
GROUP = BASE / "TdlibNotificationGroup.java"
HELPER = BASE / "TdlibNotificationHelper.java"
NOTIFICATION = BASE / "TdlibNotification.java"


def source_for(group=GROUP, helper=HELPER):
    group_methods = "\n".join(block(group, signature) for signature in (
        "public int updateGroup (", "public TdlibNotification removeNotification (",
        "public List<TdlibNotification> notifications ()", "public int getTotalCount ()",
        "public int maxNotificationId ()", "public boolean isEmpty ()",
        "public boolean isHidden ()", "public boolean isHidden (int notificationId)",
        "private void setNotificationData (", "private void increaseHiddenNotificationId (",
        "public void markAsVisible ()", "private void restoreData ()",
    ))
    helper_methods = "\n".join(block(helper, signature) for signature in (
        "public void updateGroup (", "private void onGroupChanged (",
    ))
    drop_method = block(helper, "private int dropMutedTopicNotifications (").replace(
        "moe.kirao.mgx.topics.XgramTopicMute", "Mute")
    return (ROOT / "tests/NotificationCacheHarness.java").read_text().replace(
        "/* GROUP_METHODS */", group_methods).replace(
        "/* HELPER_METHODS */", helper_methods).replace("/* DROP_METHOD */", drop_method).replace(
        "/* NOTIFICATION_HIDDEN_METHOD */", block(NOTIFICATION, "public boolean isHidden ()"))


def compile_harness(directory, source):
    java = Path(directory) / "NotificationCacheHarness.java"
    java.write_text(source)
    subprocess.run(["javac", "-Xlint:all", "-d", directory, str(java)], check=True)


class NotificationCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="notification-cache-jvm-")
        compile_harness(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, scenario):
        subprocess.run(["java", "-ea", "-cp", self.temp.name,
                        "NotificationCacheHarness", scenario], check=True)

    def test_empty_group_clears_stale_and_current_notifications_and_global_cache(self):
        self.run_case("stale-and-current")

    def test_empty_group_without_removed_ids_clears_retained_notifications(self):
        self.run_case("no-removed-ids")

    def test_nonempty_group_keeps_retained_dismissed_messages(self):
        self.run_case("nonempty")

    def test_push_replacement_preserves_hidden_boundary(self):
        self.run_case("push-replacement")

    def test_later_new_message_cannot_restore_old_empty_group_entries(self):
        self.run_case("later-new-message")

    def test_empty_unknown_group_does_not_accept_added_notifications(self):
        self.run_case("unknown-empty")

    def test_fully_filtered_topic_update_is_silent_and_not_counted(self):
        self.run_case("filtered-all")

    def test_filtered_topic_update_keeps_dismissed_group_hidden(self):
        self.run_case("filtered-hidden")

    def test_partially_filtered_update_alerts_for_real_message(self):
        self.run_case("filtered-partial")

    def test_pure_deletion_is_unchanged(self):
        self.run_case("pure-deletion")

    def test_mentions_group_reaches_the_mention_decision(self):
        self.run_case("mentions-group")

    def filter_negative(self, old, new, scenario, message):
        with tempfile.TemporaryDirectory(prefix="notification-filter-baseline-") as tmp:
            previous = Path(tmp) / HELPER.name
            text = HELPER.read_text()
            self.assertEqual(text.count(old), 1, old)
            previous.write_text(text.replace(old, new, 1))
            compile_harness(tmp, source_for(helper=previous))
            result = subprocess.run(["java", "-ea", "-cp", tmp, "NotificationCacheHarness", scenario],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)

    def test_negative_filter_without_silence_rings_and_reshows(self):
        self.filter_negative(
            "boolean isSilent = update.notificationSoundId == 0 || (droppedCount > 0 && update.addedNotifications.length == 0);",
            "boolean isSilent = update.notificationSoundId == 0;", "filtered-hidden",
            "deletion plus filtered message keeps a dismissed group hidden")

    def test_negative_filter_without_count_adjustment(self):
        self.filter_negative("update.totalCount = Math.max(0, update.totalCount - droppedCount);", "",
                             "filtered-partial", "count excludes only the filtered notification")

    def test_negative_previous_filter_rings_for_filtered_burst(self):
        text = HELPER.read_text()
        old = ("if (droppedCount > 0) {\n      // TDLib still counts the dropped notifications until it handles their RemoveNotification.\n"
               "      update.totalCount = Math.max(0, update.totalCount - droppedCount);\n    }")
        self.assertEqual(text.count(old), 1)
        with tempfile.TemporaryDirectory(prefix="notification-filter-previous-") as tmp:
            previous = Path(tmp) / HELPER.name
            previous.write_text(text.replace(old, "").replace(
                "boolean isSilent = update.notificationSoundId == 0 || (droppedCount > 0 && update.addedNotifications.length == 0);",
                "boolean isSilent = update.notificationSoundId == 0;"))
            compile_harness(tmp, source_for(helper=previous))
            result = subprocess.run(["java", "-ea", "-cp", tmp, "NotificationCacheHarness", "filtered-all"],
                                    text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fully filtered update must not re-show or ring", result.stderr)

    def test_negative_mentions_group_treated_as_messages(self):
        self.filter_negative("final boolean mentionGroup = update.type instanceof TdApi.NotificationGroupTypeMentions;",
                             "final boolean mentionGroup = false;", "mentions-group",
                             "the Mentions group is decided by mention settings")

    def test_stale_cache_regression_detects_missing_empty_group_cleanup(self):
        # A negative control removes only the fix from the production group.
        # Avoid HEAD/history dependencies: CI checks out the fixed commit shallowly.
        with tempfile.TemporaryDirectory(prefix="notification-cache-baseline-") as tmp:
            previous = Path(tmp) / GROUP.name
            cleanup = block(GROUP, "if (update.totalCount == 0)")
            previous.write_text(GROUP.read_text().replace(cleanup, "", 1))
            compile_harness(tmp, source_for(group=previous))
            result = subprocess.run(["java", "-ea", "-cp", tmp,
                                     "NotificationCacheHarness", "stale-and-current"],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("authoritative empty group must clear stale 4522", result.stderr)


if __name__ == "__main__":
    unittest.main()
