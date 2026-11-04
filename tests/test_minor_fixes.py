"""Small fixes from the review's P3 list, run with unchanged production methods on the JVM.

* MainController: an external share that arrives while the passcode is shown continues on unlock.
* TdlibNotificationManager.fixSoundUri: imported ringtones are copied with FileCopyUtils.
* TD.saveToDownloadsImpl: a file without an extension gets one from its MIME type.
No intent is sent, no ringtone is installed and nothing is written outside a temp directory.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_history_preview import method

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app/src/main/java/org/thunderdog/challegram"


def run_java(sources, main, *args):
    with tempfile.TemporaryDirectory(prefix="minor-fixes-") as tmp:
        root = Path(tmp) / "src"
        for name, text in sources.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        classes = Path(tmp) / "classes"
        subprocess.run(["javac", "-nowarn", "-d", str(classes), *map(str, root.rglob("*.java"))], check=True)
        return subprocess.run(["java", "-cp", str(classes), main, *(args or [tmp])], capture_output=True, text=True)


PASSCODE = r'''
import java.util.*;
public class PasscodeHarness {
  static class BaseActivity {
    interface PasscodeListener { void onPasscodeShowing (BaseActivity context, boolean isShowing); }
    boolean showing; final List<PasscodeListener> listeners = new ArrayList<>();
    boolean isPasscodeShowing () { return showing; }
    void addPasscodeListener (PasscodeListener l) { listeners.add(l); }
    void removePasscodeListener (PasscodeListener l) { listeners.remove(l); }
    void setShowing (boolean value) { showing = value; for (PasscodeListener l : new ArrayList<>(listeners)) l.onPasscodeShowing(this, value); }
  }
  final BaseActivity activity = new BaseActivity(); int shared;
  BaseActivity context () { return activity; }
  // The opening of MainController.shareIntentImpl, then the share itself.
  private void shareIntentImpl () {
    BaseActivity activity = context();
    /* PASSCODE_BLOCK */
    shared++;
  }
  public static void main (String[] args) {
    PasscodeHarness h = new PasscodeHarness();
    h.activity.showing = true;
    h.shareIntentImpl();
    if (h.shared != 0 || h.activity.listeners.size() != 1) throw new AssertionError("locked share must wait");
    h.activity.setShowing(false);
    if (h.shared != 1) throw new AssertionError("share must continue once unlocked");
    if (!h.activity.listeners.isEmpty()) throw new AssertionError("listener must be removed after unlocking");
    h.activity.setShowing(true); h.activity.setShowing(false);
    if (h.shared != 1) throw new AssertionError("a later lock must not repeat the share");
    System.out.println("passcode share resumes once");
  }
}
'''

RINGTONE = r'''
import java.io.*;
import java.util.*;
import org.thunderdog.challegram.util.FileCopyUtils;
public class RingtoneHarness {
  @interface NonNull {} @interface Nullable {}
  static File ringtones;
  static class Uri {
    final String value; Uri (String v) { value = v; }
    String getScheme () { return value.substring(0, value.indexOf(':')); }
    String getAuthority () { String rest = value.substring(value.indexOf("//") + 2); return rest.substring(0, rest.indexOf('/')); }
    String getPath () { String rest = value.substring(value.indexOf("//") + 2); return rest.substring(rest.indexOf('/')); }
    @Override public String toString () { return value; }
  }
  static class android { static class provider { static class Settings { static class System {
    static final Uri DEFAULT_RINGTONE_URI = new Uri("content://settings/system/ringtone"), DEFAULT_NOTIFICATION_URI = new Uri("content://settings/system/notification_sound"); } } } }
  static class Config { static final String FILE_PROVIDER_AUTHORITY = "com.ayx.mgx.provider"; }
  static class StringUtils { static boolean isEmpty (CharSequence s) { return s == null || s.length() == 0; } }
  static class UI { static Object getAppContext () { return null; } }
  static class FileProvider { static Uri getUriForFile (Object c, String authority, File f) { return new Uri("content://" + authority + "/ringtones/" + f.getName()); } }
  static class FileUtils { static boolean copy (File a, File b) { throw new AssertionError("ringtone import used the single-transfer copy"); } }
  static String sourcePath;
  static class U {
    static String tryResolveFilePath (Uri uri) { return sourcePath; }
    static File getRingtonesDir () { return ringtones; }
    static String getRingtoneName (Uri uri, String fallback) { return "tone.ogg"; }
    static boolean copyFile (Object c, Uri uri, File out) { throw new AssertionError("provider copy is the fallback only"); }
    /* U_METHODS */
  }
  /* FIX_SOUND_URI */
  public static void main (String[] args) throws Exception {
    File tmp = new File(args[0]); ringtones = new File(tmp, "ringtones"); ringtones.mkdirs();
    File source = new File(tmp, "source.ogg");
    byte[] data = new byte[200_000]; new Random(5).nextBytes(data);
    try (FileOutputStream out = new FileOutputStream(source)) { out.write(data); }
    sourcePath = source.getPath();
    Uri result = fixSoundUri(new Uri("content://media/external/audio/media/7"), true, null);
    if (result == null || !result.getPath().equals("/ringtones/tone.ogg")) throw new AssertionError("ringtone not imported: " + result);
    byte[] copied = java.nio.file.Files.readAllBytes(new File(ringtones, "tone.ogg").toPath());
    if (!Arrays.equals(copied, data)) throw new AssertionError("ringtone copy differs");
    if (fixSoundUri(result, true, null) != result) throw new AssertionError("an imported ringtone is kept");
    System.out.println("ringtone import copies completely");
  }
}
'''

DOWNLOADS = r'''
import java.io.*;
import java.util.*;
import org.thunderdog.challegram.util.FileCopyUtils;
public class DownloadsHarness {
  static File publicDownloads;
  static class Environment { static final String DIRECTORY_DOWNLOADS = "Download"; static File getExternalStoragePublicDirectory (String t) { return publicDownloads; } }
  static class BuildConfig { static final String PROJECT_NAME = "moegramX"; }
  static class FileUtils { static boolean createDirectory (File f) { return f.isDirectory() || f.mkdirs(); } }
  static class StringUtils { static boolean isEmpty (CharSequence s) { return s == null || s.length() == 0; } }
  // TDLib's GetFileExtension needs the native library; this double answers what TDLib answers for these types.
  static class TGMimeType {
    static String extensionForMimeType (String mime) { return "application/pdf".equals(mime) ? "pdf" : "image/jpeg".equals(mime) ? "jpg" : null; }
    static String mimeTypeForExtension (String extension) { return null; }
  }
  static final List<Runnable> posted = new ArrayList<>();
  static class UI { static void post (Runnable r) { posted.add(r); } }
  static class U {
    static String getFileName (String path) { int i = path.lastIndexOf('/'); return i == -1 ? path : path.substring(i + 1); }
    /* U_METHODS */
  }
  /* SAVE_METHOD */
  public static void main (String[] args) throws Exception {
    File tmp = new File(args[0]); publicDownloads = new File(tmp, "Download");
    File cache = new File(tmp, "cache"); cache.mkdirs();
    File plain = new File(cache, "report"); try (FileWriter w = new FileWriter(plain)) { w.write("pdf"); }
    File named = new File(cache, "photo.png"); try (FileWriter w = new FileWriter(named)) { w.write("png"); }
    File unknown = new File(cache, "blob"); try (FileWriter w = new FileWriter(unknown)) { w.write("?"); }
    saveToDownloadsImpl(plain, "application/pdf");
    saveToDownloadsImpl(named, "image/jpeg");
    saveToDownloadsImpl(unknown, null);
    File dir = new File(publicDownloads, "moegramX");
    Set<String> names = new TreeSet<>(Arrays.asList(Objects.requireNonNull(dir.list())));
    if (!names.equals(new TreeSet<>(Arrays.asList("report.pdf", "photo.png", "blob")))) throw new AssertionError("saved names: " + names);
    if (posted.size() != 3) throw new AssertionError("each save is announced");
    System.out.println("downloads names: " + names);
  }
}
'''

FILECOPY_LOG = "package org.thunderdog.challegram; public class Log { public static void e (String m, Throwable t) { } public static void w (String m) { } public static void w (String m, Throwable t) { } }"


class MinorFixesTest(unittest.TestCase):
    def passcode(self, text=None):
        text = text or (SRC / "ui/MainController.java").read_text(encoding="utf-8")
        block = method(text, "if (activity.isPasscodeShowing()) {")
        return run_java({"PasscodeHarness.java": PASSCODE.replace("/* PASSCODE_BLOCK */", block)}, "PasscodeHarness", "-")

    def test_locked_share_continues_on_unlock(self):
        r = self.passcode()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_negative_previous_passcode_condition(self):
        text = (SRC / "ui/MainController.java").read_text(encoding="utf-8")
        old = "          if (!isShowing) { // Unlocked\n"
        self.assertEqual(text.count(old), 1)
        r = self.passcode(text.replace(old, "          if (isShowing) {\n"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("share must continue once unlocked", r.stderr)

    def ringtone(self, text=None):
        text = text or (SRC / "telegram/TdlibNotificationManager.java").read_text(encoding="utf-8")
        u = (SRC / "U.java").read_text(encoding="utf-8")
        u_methods = "\n".join(method(u, s) for s in ("public static String getExtension (String path)",
                                                     "public static String getFileName (String path)",
                                                     "public static File newFile (File parent, String fileName, String extension)"))
        source = RINGTONE.replace("/* U_METHODS */", u_methods).replace(
            "/* FIX_SOUND_URI */", method(text, "public static Uri fixSoundUri (@NonNull Uri uri, boolean allowCopy, @Nullable String forceFileName)"))
        return run_java({"RingtoneHarness.java": source,
                         "org/thunderdog/challegram/Log.java": FILECOPY_LOG,
                         "org/thunderdog/challegram/util/FileCopyUtils.java": (SRC / "util/FileCopyUtils.java").read_text(encoding="utf-8")},
                        "RingtoneHarness")

    def test_ringtone_import_uses_verified_copy(self):
        r = self.ringtone()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_negative_ringtone_single_transfer_copy(self):
        text = (SRC / "telegram/TdlibNotificationManager.java").read_text(encoding="utf-8")
        old = "(fileAccessible && FileCopyUtils.copy(new File(filePath), outputFile))"
        self.assertEqual(text.count(old), 1)
        r = self.ringtone(text.replace(old, "(fileAccessible && FileUtils.copy(new File(filePath), outputFile))"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("single-transfer copy", r.stderr)

    def downloads(self, text=None):
        text = text or (SRC / "data/TD.java").read_text(encoding="utf-8")
        u = (SRC / "U.java").read_text(encoding="utf-8")
        u_methods = "\n".join(method(u, s) for s in ("public static String getExtension (String path)",
                                                     "public static File newFile (File parent, String fileName)",
                                                     "public static File newFile (File parent, String fileName, String extension)"))
        save = method(text, "private static void saveToDownloadsImpl (final File sourceFile, final String sourceMimeType)")
        # Only the Android announcement after the copy is replaced by a record of it.
        start = save.index("    UI.post(() -> {")
        save = save[:start] + "    UI.post(() -> { });\n  }"
        return run_java({"DownloadsHarness.java": DOWNLOADS.replace("/* U_METHODS */", u_methods).replace("/* SAVE_METHOD */", save),
                         "org/thunderdog/challegram/Log.java": FILECOPY_LOG,
                         "org/thunderdog/challegram/util/FileCopyUtils.java": (SRC / "util/FileCopyUtils.java").read_text(encoding="utf-8")},
                        "DownloadsHarness")

    def test_extensionless_download_gets_mime_extension(self):
        r = self.downloads()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_negative_previous_extension_lookup(self):
        text = (SRC / "data/TD.java").read_text(encoding="utf-8")
        old = "TGMimeType.extensionForMimeType(sourceMimeType)"
        self.assertEqual(text.count(old), 1)
        r = self.downloads(text.replace(old, "TGMimeType.mimeTypeForExtension(extension)"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("saved names", r.stderr)


if __name__ == "__main__":
    unittest.main()
