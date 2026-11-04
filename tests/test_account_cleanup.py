"""Slot-keyed Moex preferences across Close/restart and logout; JVM only, no account is touched.

Compiles the real TdApi, Tdlib's authorization-status mapping and cleanup trigger, the
TdlibListeners dispatch, TdlibSettingsManager's cleanup/restart methods, MoexConfig's
Shadow Ban list methods and the real ForumSettings class. Storage is an in-memory
LevelDB double; no login, logout or device action happens.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_history_preview import method

ROOT = Path(__file__).resolve().parents[1]
TG = ROOT / "app/src/main/java/org/thunderdog/challegram/telegram"
MOEX = ROOT / "app/src/main/java/moe/kirao/mgx"
TDAPI = ROOT / "tdlib/src/main/java/org/drinkless/tdlib/TdApi.java"

FILES = {
    "androidx/annotation/Nullable.java": "package androidx.annotation; public @interface Nullable {}",
    "androidx/annotation/NonNull.java": "package androidx.annotation; public @interface NonNull {}",
    "androidx/annotation/IntDef.java": "package androidx.annotation; public @interface IntDef { int[] value() default {}; boolean flag() default false; boolean open() default false; }",
    "android/content/SharedPreferences.java": """package android.content;
public interface SharedPreferences { interface Editor { Editor remove (String key); void apply (); } }""",
    "me/vkryl/leveldb/LevelDB.java": """package me.vkryl.leveldb;
import java.util.*;
public class LevelDB {
  public final TreeMap<String, Object> values = new TreeMap<>();
  public void putInt (String k, int v) { values.put(k, v); } public int getInt (String k, int d) { Object v = values.get(k); return v != null ? (Integer) v : d; }
  public void putBoolean (String k, boolean v) { values.put(k, v); } public boolean getBoolean (String k, boolean d) { Object v = values.get(k); return v != null ? (Boolean) v : d; }
  public void putLongArray (String k, long[] v) { values.put(k, v.clone()); } public long[] getLongArray (String k) { long[] v = (long[]) values.get(k); return v != null ? v.clone() : null; }
  public void remove (String k) { values.remove(k); } public boolean contains (String k) { return values.containsKey(k); }
  public int removeByAnyPrefix (String... prefixes) { int n = 0; for (Iterator<String> i = values.keySet().iterator(); i.hasNext(); ) { String k = i.next(); for (String p : prefixes) if (k.startsWith(p)) { i.remove(); n++; break; } } return n; }
}""",
    "org/thunderdog/challegram/unsorted/Settings.java": """package org.thunderdog.challegram.unsorted;
import android.content.SharedPreferences; import me.vkryl.leveldb.LevelDB;
public class Settings {
  static final Settings INSTANCE = new Settings(); public static Settings instance () { return INSTANCE; }
  public final LevelDB pmc = new LevelDB(); public LevelDB pmc () { return pmc; }
  public SharedPreferences.Editor edit () { return new SharedPreferences.Editor() {
    public SharedPreferences.Editor remove (String key) { pmc.remove(key); return this; } public void apply () { } }; }
  public void deleteWallpapers (Object tdlib, SharedPreferences.Editor editor) { }
  public void removeScrollPositions (int accountId, SharedPreferences.Editor editor) { }
  public void removeByAnyPrefix (String[] prefixes, SharedPreferences.Editor editor) { pmc.removeByAnyPrefix(prefixes); }
}""",
}

HARNESS = r'''
import android.content.SharedPreferences;
import java.util.*;
import me.vkryl.leveldb.LevelDB;
import moe.kirao.mgx.topics.ForumSettings;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.CleanupStartupDelegate;
import org.thunderdog.challegram.unsorted.Settings;

public class CleanupHarness {
  @interface Status { int UNKNOWN = 0, UNAUTHORIZED = 1, READY = 2; }
  static class Td {
    static void assertAuthorizationState_ba756b5f () { }
    static RuntimeException unsupported (Object o) { return new UnsupportedOperationException(String.valueOf(o)); }
  }
  static class Log { static void i (String format, Object... args) { } }
  static class Config { static final boolean CHAT_FOLDERS_APPEARANCE_IS_GLOBAL = false; }
  static final List<Integer> invalidated = new ArrayList<>();
  static final List<String> notified = new ArrayList<>();
  static class MoexShadowUnreadManager { static void invalidateAccount (int accountId) { invalidated.add(accountId); } }

  static class MoexConfig {
    static final MoexConfig INSTANCE = new MoexConfig(); static MoexConfig instance () { return INSTANCE; }
    final LevelDB config = new LevelDB();
    /* SHADOW_PREFIX */
    void notifyClientListeners (String key, Object newValue, Object oldValue) { notified.add(key + ":" + Arrays.toString((long[]) oldValue) + "->" + Arrays.toString((long[]) newValue)); }
    /* MOEX_METHODS */
  }

  static class TdlibListeners {
    final List<CleanupStartupDelegate> componentDelegates = new ArrayList<>();
    /* LISTENER_METHODS */
  }

  static class Tdlib {
    final int accountId; final TdlibListeners listeners = new TdlibListeners(); TdApi.AuthorizationState authorizationState;
    Tdlib (int accountId) { this.accountId = accountId; }
    int id () { return accountId; }
    TdlibListeners listeners () { return listeners; }
    /* GET_STATUS */
    // The two Tdlib.updateAuthState steps relevant here: the unchanged cleanup trigger, and the
    // restart that its AuthorizationStateClosed branch performs after closing the client.
    void updateAuthState (TdApi.AuthorizationState newAuthState) {
      final int prevStatus = getStatus(authorizationState);
      authorizationState = newAuthState;
      final int newStatus = getStatus(newAuthState);
      if (newAuthState instanceof TdApi.AuthorizationStateClosed) listeners().performRestart();
      /* CLEANUP_TRIGGER */
    }
  }

  static class TdlibSettingsManager implements CleanupStartupDelegate {
    final Tdlib tdlib; final List<Object> wallpapers = new ArrayList<>();
    final Map<Long, Long> remoteToLocalChatIds = new HashMap<>(), localToRemoteChatIds = new HashMap<>();
    int loads, unregistered;
    TdlibSettingsManager (Tdlib tdlib) { this.tdlib = tdlib; }
    static String key (String key, int accountId) { return accountId != 0 ? accountId + "_" + key : key; }
    void unregisterDevice (int accountId) { unregistered++; }
    void load () { loads++; }
    /* SETTINGS_FIELDS */
    /* SETTINGS_METHODS */
  }

  static int checks;
  static void check (boolean value, String message) { checks++; if (!value) throw new AssertionError(message); }

  public static void main (String[] args) {
    MoexConfig config = MoexConfig.instance(); ForumSettings forum = ForumSettings.instance();
    config.setShadowBannedUsers(1, new long[] {42}); config.setShadowBannedUsers(11, new long[] {99});
    forum.setForumLayout(1, -100, ForumSettings.FORUM_LAYOUT_TABS); forum.setLastForumTab(1, -100, 3); forum.setForumTabsOnSide(1, -100, true);
    forum.setForumLayout(11, -100, ForumSettings.FORUM_LAYOUT_LIST);
    invalidated.clear(); notified.clear();

    Tdlib slot = new Tdlib(1); TdlibSettingsManager settings = new TdlibSettingsManager(slot);
    slot.listeners.componentDelegates.add(settings);
    slot.updateAuthState(new TdApi.AuthorizationStateWaitTdlibParameters());
    slot.updateAuthState(new TdApi.AuthorizationStateReady());
    // Close and reconnect the same user (service/foreground mode switch, network changes).
    slot.updateAuthState(new TdApi.AuthorizationStateClosing());
    slot.updateAuthState(new TdApi.AuthorizationStateClosed());
    slot.updateAuthState(new TdApi.AuthorizationStateWaitTdlibParameters());
    slot.updateAuthState(new TdApi.AuthorizationStateReady());
    check(config.isShadowBanned(1, 42) && forum.forumLayout(1, -100) == ForumSettings.FORUM_LAYOUT_TABS &&
      forum.lastForumTab(1, -100, 0) == 3 && forum.forumTabsOnSide(1, -100), "Close and reconnect must keep preferences");
    check(settings.loads == 0 && invalidated.isEmpty(), "no cleanup without a logout");

    // A real logout: TDLib reports AuthorizationStateLoggingOut, then a fresh client asks for a phone number.
    slot.updateAuthState(new TdApi.AuthorizationStateLoggingOut());
    check(!config.isShadowBanned(1, 42) && config.getShadowBannedUsers(1).length == 0, "slot reuse must not inherit the Shadow Ban list");
    check(forum.forumLayout(1, -100) == ForumSettings.FORUM_LAYOUT_GROUP && forum.lastForumTab(1, -100, -1) == -1 &&
      !forum.forumTabsOnSide(1, -100), "slot reuse must not inherit topic layouts");
    check(invalidated.equals(List.of(1)) && notified.equals(List.of("shadow_banned_users_1:[42]->[]")), "open filters drop the old list");
    check(config.isShadowBanned(11, 99) && forum.forumLayout(11, -100) == ForumSettings.FORUM_LAYOUT_LIST, "other slots keep their data");
    slot.updateAuthState(new TdApi.AuthorizationStateClosing());
    slot.updateAuthState(new TdApi.AuthorizationStateClosed());
    slot.updateAuthState(new TdApi.AuthorizationStateWaitTdlibParameters());
    slot.updateAuthState(new TdApi.AuthorizationStateWaitPhoneNumber());
    check(notified.size() == 1 && invalidated.size() == 1, "an empty slot is cleaned up idempotently");
    slot.updateAuthState(new TdApi.AuthorizationStateReady()); // the next user logs in
    check(config.getShadowBannedUsers(1).length == 0, "next login starts empty");
    config.setShadowBanned(1, 5, true);
    check(config.isShadowBanned(1, 5), "the new user's list works");
    System.out.println("account cleanup: " + checks + " checks passed");
  }
}
'''


def sources(settings_text=None):
    tdlib = (TG / "Tdlib.java").read_text(encoding="utf-8")
    listeners = (TG / "TdlibListeners.java").read_text(encoding="utf-8")
    settings = settings_text or (TG / "TdlibSettingsManager.java").read_text(encoding="utf-8")
    moex = (MOEX / "MoexConfig.java").read_text(encoding="utf-8")
    trigger = method(tdlib, "if (prevStatus != Status.UNAUTHORIZED && newStatus == Status.UNAUTHORIZED) {")
    cleanup = method(settings, "public void onPerformUserCleanup ()").replace("moe.kirao.mgx.MoexConfig.instance()", "MoexConfig.instance()")
    restart = method(settings, "public void onPerformRestart ()")
    constants = sorted(set(re.findall(r"\bkey\(([A-Z][A-Z0-9_]+), accountId\)", cleanup)))
    fields = sorted(set(re.findall(r"\b(_[A-Za-z0-9]+) =", cleanup)))
    declarations = "\n".join([f'    static final String {c} = "{c.lower()}";' for c in constants] +
                             [f"    Object {f};" for f in fields])
    moex_methods = "\n".join(method(moex, s) for s in (
        "private static String shadowBannedUsersKey (", "public synchronized boolean isShadowBanned (",
        "public synchronized void setShadowBanned (", "public synchronized long[] getShadowBannedUsers (",
        "public synchronized void setShadowBannedUsers (", "public synchronized void clearAccountData (",
        "public void remove (String key)", "public void putLongArray (", "public long[] getLongArray (",
    ))
    prefix = re.search(r'private static final String KEY_SHADOW_BANNED_USERS_PREFIX = "[^"]+";', moex).group(0)
    return (HARNESS.replace("/* CLEANUP_TRIGGER */", trigger)
            .replace("/* GET_STATUS */", method(tdlib, "private static @Status int getStatus ("))
            .replace("/* LISTENER_METHODS */", method(listeners, "public void performCleanup ()") + "\n" +
                     method(listeners, "public void performRestart ()"))
            .replace("/* SETTINGS_FIELDS */", declarations)
            .replace("/* SETTINGS_METHODS */", cleanup + "\n" + restart)
            .replace("/* SHADOW_PREFIX */", prefix)
            .replace("/* MOEX_METHODS */", moex_methods))


class AccountCleanupTest(unittest.TestCase):
    def run_harness(self, harness):
        with tempfile.TemporaryDirectory(prefix="account-cleanup-") as tmp:
            src = Path(tmp) / "src"
            files = dict(FILES)
            files["org/drinkless/tdlib/TdApi.java"] = TDAPI.read_text(encoding="utf-8")
            files["org/thunderdog/challegram/telegram/CleanupStartupDelegate.java"] = (TG / "CleanupStartupDelegate.java").read_text(encoding="utf-8")
            files["moe/kirao/mgx/topics/ForumSettings.java"] = (MOEX / "topics/ForumSettings.java").read_text(encoding="utf-8")
            files["CleanupHarness.java"] = harness
            for name, text in files.items():
                path = src / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            classes = Path(tmp) / "classes"
            subprocess.run(["javac", "-nowarn", "-d", str(classes), *map(str, src.rglob("*.java"))], check=True)
            return subprocess.run(["java", "-cp", str(classes), "CleanupHarness"], capture_output=True, text=True)

    def test_logout_clears_slot_preferences_but_restart_keeps_them(self):
        result = self.run_harness(sources())
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_negative_previous_cleanup_leaks_to_next_login(self):
        text = (TG / "TdlibSettingsManager.java").read_text(encoding="utf-8")
        old = ("    moe.kirao.mgx.MoexConfig.instance().clearAccountData(accountId);\n"
               "    moe.kirao.mgx.topics.ForumSettings.instance().clearAccount(accountId);\n")
        self.assertEqual(text.count(old), 1)
        result = self.run_harness(sources(settings_text=text.replace(old, "")))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("slot reuse must not inherit the Shadow Ban list", result.stderr)


if __name__ == "__main__":
    unittest.main()
