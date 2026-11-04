"""Account numbers carried by intents to the exported MainActivity; JVM only, no intent is sent.

The OPEN_MAIN / OPEN_CHAT / OPEN_PLAYER branches of handleIntent, the account check and
openPlayerController run unchanged with TdlibManager's real hasAccount/account lookups.
The opening sinks start like production (account lookup first) and then only record.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_history_preview import method

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY = ROOT / "app/src/main/java/org/thunderdog/challegram/MainActivity.java"
MANAGER = ROOT / "app/src/main/java/org/thunderdog/challegram/telegram/TdlibManager.java"

HARNESS = r'''
import java.util.*;
public class IntentAccountHarness {
  static class Log { static void w (String f, Object... a) { } static void e (String f, Object... a) { } }
  static class StringUtils { static int parseInt (String s) { try { return Integer.parseInt(s); } catch (NumberFormatException e) { return 0; } } }
  static class Intents { static final String ACTION_OPEN_MAIN = "com.ayx.mgx.OPEN_MAIN", ACTION_OPEN_CHAT = "com.ayx.mgx.OPEN_CHAT", ACTION_OPEN_PLAYER = "com.ayx.mgx.OPEN_PLAYER"; }
  static class XgramForums { static final String EXTRA_NOTIFICATION_TOPIC_ID = "topic"; }
  static class TdlibSettingsManager { static long getRemoteChatId (int accountId, long localChatId) { return localChatId + 1000; } }
  static class Intent {
    final Map<String, Object> extras = new HashMap<>();
    Intent put (String k, Object v) { extras.put(k, v); return this; }
    int getIntExtra (String k, int d) { Object v = extras.get(k); return v != null ? (Integer) v : d; }
    long getLongExtra (String k, long d) { Object v = extras.get(k); return v != null ? (Long) v : d; }
  }
  static class Tdlib {
    final int id; Tdlib (int id) { this.id = id; } int id () { return id; }
    void awaitInitialization (Runnable r) { r.run(); } void incrementUiReferenceCount () { } void decrementUiReferenceCount () { }
  }
  static class TdlibAccount {
    static final int NO_ID = -1; final int id; boolean unauthorized;
    TdlibAccount (int id) { this.id = id; } Tdlib tdlib () { return new Tdlib(id); } boolean isUnauthorized () { return unauthorized; }
  }
  static class TdlibManager {
    static final TdlibManager INSTANCE = new TdlibManager();
    final List<TdlibAccount> accounts = new ArrayList<>(); int current;
    static TdlibManager instance () { return INSTANCE; }
    static TdlibManager instanceForAccountId (int id) { return INSTANCE; }
    TdlibAccount currentAccount () { return accounts.get(current); }
    /* MANAGER_METHODS */
  }
  static class Handler { void post (Runnable r) { r.run(); } }
  static class PlaybackController extends ViewController<Object> { PlaybackController (Object c, Tdlib t) { } int prepare () { return 0; } }
  static class ViewController<T> { }
  static class Navigation { ViewController<?> getCurrentStackItem () { return null; } boolean isEmpty () { return false; } }
  final Handler handler = new Handler(); final Navigation navigation = new Navigation(); Tdlib tdlib = new Tdlib(0);
  final List<String> opened = new ArrayList<>();
  void initDefault (int id, boolean b) { }
  void navigateToSafely (Object c) { opened.add("player"); }
  void openMainController (int accountId) { opened.add("main:" + accountId); }
  // Production starts with this lookup, which threw IndexOutOfBoundsException for a foreign number.
  void openMessagesController (int accountId, long chatId, long messageId, int topicId) {
    TdlibManager.instanceForAccountId(accountId).account(accountId).tdlib();
    opened.add("chat:" + accountId + ":" + chatId);
  }
  /* ACCOUNT_CHECK */
  /* PLAYER */
  boolean handle (String action, Intent intent) {
    /* OPEN_MAIN */
    /* OPEN_CHAT */
    /* OPEN_PLAYER */
    return false;
  }

  static int checks;
  static void check (boolean v, String m) { checks++; if (!v) throw new AssertionError(m); }
  public static void main (String[] args) {
    TdlibManager m = TdlibManager.INSTANCE;
    for (int i = 0; i < 3; i++) m.accounts.add(new TdlibAccount(i));
    m.accounts.get(2).unauthorized = true; m.current = 1;
    IntentAccountHarness a = new IntentAccountHarness();
    for (int bad : new int[] {99, 3, -5, Integer.MAX_VALUE}) {
      a.opened.clear();
      check(!a.handle(Intents.ACTION_OPEN_CHAT, new Intent().put("account_id", bad).put("chat_id", 7L)), "foreign account opens no chat");
      a.handle(Intents.ACTION_OPEN_PLAYER, new Intent().put("account_id", bad));
      check(a.handle(Intents.ACTION_OPEN_MAIN, new Intent().put("account_id", bad)), "main still opens");
      check(a.opened.equals(List.of("main:1")), "foreign numbers fall back to the current account, got " + a.opened);
    }
    a.opened.clear();
    check(!a.handle(Intents.ACTION_OPEN_CHAT, new Intent().put("account_id", 2).put("chat_id", 7L)), "logged-out slot opens no chat");
    a.handle(Intents.ACTION_OPEN_PLAYER, new Intent().put("account_id", 2));
    check(a.opened.isEmpty(), "logged-out slot opens no player");
    check(a.handle(Intents.ACTION_OPEN_CHAT, new Intent().put("account_id", 0).put("chat_id", 7L)), "notification for a known account opens");
    check(a.handle(Intents.ACTION_OPEN_CHAT, new Intent().put("account_id", 0).put("local_id", 5L)), "local chat id resolves");
    check(a.handle(Intents.ACTION_OPEN_MAIN + ".0", new Intent()), "suffix account");
    a.handle(Intents.ACTION_OPEN_PLAYER, new Intent().put("account_id", 0));
    check(a.opened.equals(List.of("chat:0:7", "chat:0:1005", "main:0", "player")), "valid intents keep working, got " + a.opened);
    System.out.println("intent accounts: " + checks + " checks passed");
  }
}
'''


def sources(activity_text=None):
    activity = activity_text or ACTIVITY.read_text(encoding="utf-8")
    manager = MANAGER.read_text(encoding="utf-8")
    return (HARNESS
            .replace("/* MANAGER_METHODS */", method(manager, "public boolean hasAccount (int accountId)") + "\n" +
                     method(manager, "public TdlibAccount account (int accountId)"))
            .replace("/* ACCOUNT_CHECK */", method(activity, "private static boolean isIntentAccount (")
                     if "private static boolean isIntentAccount (" in activity else "")
            .replace("/* PLAYER */", method(activity, "private void openPlayerController (int accountId)"))
            .replace("/* OPEN_MAIN */", method(activity, "if (action.startsWith(Intents.ACTION_OPEN_MAIN)) {"))
            .replace("/* OPEN_CHAT */", method(activity, "if (action.startsWith(Intents.ACTION_OPEN_CHAT)) {")
                     .replace("moe.kirao.mgx.topics.XgramForums", "XgramForums"))
            .replace("/* OPEN_PLAYER */", method(activity, "if (action.startsWith(Intents.ACTION_OPEN_PLAYER)) {")))


class IntentAccountTest(unittest.TestCase):
    def run_harness(self, source):
        with tempfile.TemporaryDirectory(prefix="intent-account-") as tmp:
            java = Path(tmp) / "IntentAccountHarness.java"
            java.write_text(source, encoding="utf-8")
            subprocess.run(["javac", "-d", tmp, str(java)], check=True)
            return subprocess.run(["java", "-cp", tmp, "IntentAccountHarness"], capture_output=True, text=True)

    def test_foreign_and_logged_out_accounts_are_ignored(self):
        result = self.run_harness(sources())
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_negative_previous_open_chat_crashes(self):
        text = ACTIVITY.read_text(encoding="utf-8")
        old = ('      if (!isIntentAccount(accountId, true)) {\n'
               '        Log.e("Cannot open chat, unknown or logged out account: %d", accountId);\n'
               '        return false;\n      }\n')
        self.assertEqual(text.count(old), 1)
        previous = text.replace(old, "").replace("      if (chatId != 0) {\n        openMessagesController(",
                                                 "      if (accountId != TdlibAccount.NO_ID && chatId != 0) {\n        openMessagesController(")
        result = self.run_harness(sources(previous))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IndexOutOfBoundsException", result.stderr)


if __name__ == "__main__":
    unittest.main()
