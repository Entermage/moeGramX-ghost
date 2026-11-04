"""Own content URIs are allowed back in only after "Open with" actually handed them out; JVM only.

Runs U.makeUriForFile/canOpenFile and both Intents.openFile methods, copied verbatim from the sources, with the
whole OfferedUris class. android.net.Uri, Build, Intent, PackageManager, permissions and the activity
launch are minimal doubles, so nothing is opened, granted or sent.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app/src/main/java/org/thunderdog/challegram"
U_JAVA = SRC / "U.java"
INTENTS_JAVA = SRC / "tool/Intents.java"
OFFERED_JAVA = SRC / "util/OfferedUris.java"


def method(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


URI = r'''package android.net;
public class Uri {
  private final String value;
  private Uri (String value) { this.value = value; }
  public static Uri parse (String value) { return new Uri(value); }
  public static Uri fromFile (java.io.File file) { return new Uri("file://" + file.getPath()); }
  public String getScheme () { int i = value.indexOf(':'); return i == -1 ? null : value.substring(0, i); }
  public Uri normalizeScheme () { String s = getScheme(); return s == null ? this : new Uri(s.toLowerCase(java.util.Locale.ROOT) + value.substring(s.length())); }
  @Override public String toString () { return value; }
  @Override public boolean equals (Object o) { return o instanceof Uri && ((Uri) o).value.equals(value); }
  @Override public int hashCode () { return value.hashCode(); }
}
'''

NULLABLE = "package androidx.annotation; public @interface Nullable { }\n"

HARNESS = r'''
import android.net.Uri;
import androidx.annotation.Nullable;
import java.io.File;
import java.util.*;
import org.thunderdog.challegram.util.OfferedUris;

public class Harness {
  static final String AUTHORITY = "content://com.ayx.mgx.provider/";

  static class Build {
    static class VERSION { static int SDK_INT = 34; }
    static class VERSION_CODES { static final int KITKAT = 19, N = 24; }
  }
  static class Toast { static final int LENGTH_LONG = 1; }
  static class Log {
    static void e (String message, Throwable t) { }
    static void e (String format, Object... args) { }
  }
  static class StringUtils {
    static boolean isEmpty (String s) { return s == null || s.isEmpty(); }
    static boolean equalsOrBothEmpty (String a, String b) { return isEmpty(a) ? isEmpty(b) : a.equals(b); }
  }
  interface RunnableBool { void runWithBool (boolean value); }
  static class Permissions {
    boolean ask; RunnableBool pending;
    boolean requestReadExternalStorage (File file, RunnableBool after) {
      if (!ask) return false;
      pending = after; return true;
    }
  }
  static class BaseActivity { final Permissions permissions = new Permissions(); Permissions permissions () { return permissions; } }
  static class ActivityInfo { String packageName = "viewer"; }
  static class ResolveInfo { ActivityInfo activityInfo = new ActivityInfo(); }
  static class PackageManager {
    static final int MATCH_DEFAULT_ONLY = 0x10000;
    boolean resolves = true;
    List<ResolveInfo> queryIntentActivities (Intent intent, int flags) { return Collections.singletonList(new ResolveInfo()); }
  }
  static class AppContext {
    final PackageManager pm = new PackageManager();
    PackageManager getPackageManager () { return pm; }
    void grantUriPermission (String pkg, Uri uri, int flags) { }
    void revokeUriPermission (Uri uri, int flags) { }
  }
  static class Intent {
    static final String ACTION_VIEW = "android.intent.action.VIEW", ACTION_INSTALL_PACKAGE = "android.intent.action.INSTALL_PACKAGE";
    static final int FLAG_GRANT_READ_URI_PERMISSION = 1;
    final String action; Uri data; String type; int flags;
    Intent (String action) { this.action = action; }
    void setDataAndType (Uri data, String type) { this.data = data; this.type = type; }
    void setFlags (int flags) { this.flags = flags; }
    Object resolveActivity (PackageManager pm) { return pm.resolves ? "viewer" : null; }
  }
  static class UI {
    static final AppContext app = new AppContext();
    // Outcomes of the next launches: true = started, false = throws like ActivityNotFoundException.
    static final ArrayDeque<Boolean> outcomes = new ArrayDeque<>();
    static final List<Intent> started = new ArrayList<>();
    static int attempts;
    static AppContext getAppContext () { return app; }
    static void startActivity (Intent intent) {
      attempts++;
      if (!outcomes.isEmpty() && !outcomes.poll()) throw new RuntimeException("No Activity found to handle Intent");
      // A launch of this app's own entry is delivered after the caller returns; nothing is checked here.
      started.add(intent);
    }
    static void showToast (String text, int duration) { }
  }

  static class U {
    static Uri contentUriFromFile (File file) { return Uri.parse(AUTHORITY + "files" + file.getPath()); }
    static String resolveMimeType (String path) { return path.endsWith(".txt") ? "text/plain" : null; }
    /* U */
  }

  static class Intents {
    private static @Nullable ArrayList<Uri> openedFiles;
    /* INTENTS */
  }

  static int checks;
  static void check (boolean b, String m) { checks++; if (!b) throw new AssertionError(m); }
  static void reset () { UI.outcomes.clear(); UI.started.clear(); UI.attempts = 0; UI.app.pm.resolves = true; }
  static Uri uri (File f) { return U.contentUriFromFile(f); }

  public static void main (String[] args) {
    File dir = new File("/data/user/0/com.ayx.mgx/files/documents");
    File probed = new File(dir, "probed.txt"), opened = new File(dir, "opened.txt"), sibling = new File(dir, "sibling.txt");
    BaseActivity activity = new BaseActivity();

    // Building a URI or checking whether "Open with" is available hands nothing out.
    reset();
    check(U.canOpenFile(probed, "text/plain"), "menu availability check");
    check(uri(probed).equals(U.makeUriForFile(probed, "text/plain", false)), "URI of the probed file");
    check(UI.attempts == 0, "probing launches nothing");
    check(!OfferedUris.wasOffered(uri(probed)), "availability check granted external re-entry without an actual offer");

    // Explicit "Open with" that starts: exactly that URI comes back in, nothing else.
    reset();
    check(Intents.openFile(activity, opened, "text/plain"), "open succeeds");
    check(UI.started.size() == 1 && UI.started.get(0).data.equals(uri(opened)), "launched with the file's URI");
    check(OfferedUris.wasOffered(uri(opened)), "the URI just handed to \"Open with\" must be accepted back");
    check(!OfferedUris.wasOffered(uri(sibling)), "a sibling file in the same directory was allowed");
    check(!OfferedUris.wasOffered(Uri.parse(AUTHORITY + "files" + dir.getPath())), "the directory was allowed");
    check(!OfferedUris.wasOffered(Uri.parse(AUTHORITY + "files" + dir.getPath() + "/")), "the directory prefix was allowed");
    check(!OfferedUris.wasOffered(Uri.parse(uri(opened) + "-x")), "a URI extending the offered one was allowed");
    check(!OfferedUris.wasOffered(Uri.fromFile(opened)), "the file:// form was allowed");
    check(!OfferedUris.wasOffered(uri(probed)), "the earlier probe is still not allowed");

    // No app resolves: every retry fails, nothing handed out.
    File unresolved = new File(dir, "unresolved.txt");
    reset(); UI.app.pm.resolves = false;
    check(!Intents.openFile(activity, unresolved, "text/plain"), "open without a resolver fails");
    check(UI.attempts == 0, "nothing launched without a resolver");
    check(!OfferedUris.wasOffered(uri(unresolved)), "a URI no app was found for was allowed");

    // The launch itself fails on the first attempt and on every retry.
    File failing = new File(dir, "failing.txt");
    reset(); UI.outcomes.addAll(Arrays.asList(false, false, false));
    check(!Intents.openFile(activity, failing, "text/plain"), "open fails when every launch throws");
    check(UI.attempts == 2 && UI.started.isEmpty(), "first attempt and the wildcard retry both throw: " + UI.attempts);
    check(!OfferedUris.wasOffered(uri(failing)), "a failed launch allowed the URI");

    // First launch throws, the wildcard retry starts: the URI that was actually handed out is allowed.
    File retried = new File(dir, "retried.txt");
    reset(); UI.outcomes.addAll(Arrays.asList(false, true));
    check(Intents.openFile(activity, retried, "text/plain"), "retry succeeds");
    check(UI.attempts == 2 && UI.started.size() == 1 && "text/*".equals(UI.started.get(0).type), "retried with text/*");
    check(OfferedUris.wasOffered(uri(retried)), "the URI handed out by the successful retry must be accepted back");

    // Waiting for the storage permission hands nothing out; a denial keeps it that way.
    File denied = new File(dir, "denied.txt");
    reset(); activity.permissions.ask = true;
    check(!Intents.openFile(activity, denied, "text/plain"), "open defers to the permission request");
    check(UI.attempts == 0 && !OfferedUris.wasOffered(uri(denied)), "a pending permission request allowed the URI");
    activity.permissions.ask = false; activity.permissions.pending.runWithBool(false);
    check(UI.attempts == 0 && !OfferedUris.wasOffered(uri(denied)), "a denied permission allowed the URI");

    // Granted later: the deferred open starts and only then allows the URI.
    File granted = new File(dir, "granted.txt");
    reset(); activity.permissions.ask = true;
    check(!Intents.openFile(activity, granted, "text/plain"), "open defers again");
    check(!OfferedUris.wasOffered(uri(granted)), "allowed before the permission was granted");
    activity.permissions.ask = false; activity.permissions.pending.runWithBool(true);
    check(UI.started.size() == 1 && OfferedUris.wasOffered(uri(granted)), "the deferred open must allow the URI it handed out");

    // Still nothing else got in.
    for (File f : new File[] {probed, sibling, unresolved, failing, denied}) {
      check(!OfferedUris.wasOffered(uri(f)), "not handed out but allowed: " + f.getName());
    }
    System.out.println("offered URI entry: " + checks + " checks passed");
  }
}
'''


def harness(u_text=None, intents_text=None):
    u_text = u_text or U_JAVA.read_text(encoding="utf-8")
    intents_text = intents_text or INTENTS_JAVA.read_text(encoding="utf-8")
    u = "\n".join(method(u_text, s) for s in (
        "public static Uri makeUriForFile (", "public static boolean canOpenFile ("))
    intents = "\n".join(method(intents_text, s) for s in (
        "private static void revokeFileReadPermission (",
        "public static boolean openFile (final BaseActivity context, File file",
        "private static boolean openFile (final BaseActivity context, final File file"))
    return HARNESS.replace("/* U */", u).replace("/* INTENTS */", intents)


class OfferedUriEntryTest(unittest.TestCase):
    def run_harness(self, u_text=None, intents_text=None):
        sources = {
            "android/net/Uri.java": URI,
            "androidx/annotation/Nullable.java": NULLABLE,
            "org/thunderdog/challegram/util/OfferedUris.java": OFFERED_JAVA.read_text(encoding="utf-8"),
            "Harness.java": harness(u_text, intents_text),
        }
        with tempfile.TemporaryDirectory(prefix="offered-uri-") as tmp:
            out = Path(tmp)
            for name, content in sources.items():
                path = out / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            compiled = subprocess.run(["javac", "-d", tmp, *[str(out / name) for name in sources]],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            return subprocess.run(["java", "-ea", "-cp", tmp, "Harness"], capture_output=True, text=True)

    def test_only_actual_offer_is_allowed(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_negative_registration_in_make_uri(self):
        # The first-pass location: every URI built, including the menu's availability check, was allowed.
        u_text = U_JAVA.read_text(encoding="utf-8")
        intents_text = INTENTS_JAVA.read_text(encoding="utf-8")
        old_u = u_text.replace(
            "    return contentUriFromFile(file);\n  }\n\n  public static boolean canOpenFile",
            "    Uri uri = contentUriFromFile(file);\n"
            "    org.thunderdog.challegram.util.OfferedUris.remember(uri); // \"Open with\" may pick this app\n"
            "    return uri;\n  }\n\n  public static boolean canOpenFile")
        old_intents = intents_text.replace("        OfferedUris.remember(uri);\n", "")
        self.assertNotEqual(old_u, u_text)
        self.assertNotEqual(old_intents, intents_text)
        result = self.run_harness(old_u, old_intents)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("availability check granted external re-entry without an actual offer", result.stderr)

    def test_negative_registration_before_launch(self):
        # Registering when the intent is built rather than once it started lets a failed launch in.
        text = INTENTS_JAVA.read_text(encoding="utf-8")
        early = text.replace("        OfferedUris.remember(uri);\n", "") \
                    .replace("      intent.setDataAndType(uri, mimeType);\n",
                             "      intent.setDataAndType(uri, mimeType);\n      OfferedUris.remember(uri);\n")
        self.assertEqual(early.count("OfferedUris.remember(uri);"), 1)
        self.assertNotEqual(early, text)
        result = self.run_harness(intents_text=early)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("a URI no app was found for was allowed", result.stderr)


if __name__ == "__main__":
    unittest.main()
