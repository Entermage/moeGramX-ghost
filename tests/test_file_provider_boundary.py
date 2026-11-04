"""FileProvider root boundaries with the unchanged path-strategy methods; JVM only.

android.net.Uri is a minimal double (paths in these fixtures need no escaping); the
canonical-path and root checks run on real files in a temporary directory.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_history_preview import method

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "app/src/main/java/org/thunderdog/challegram/FileProvider.java"

HARNESS = r'''
import java.io.*;
import java.util.*;
public class ProviderHarness {
  static class Uri {
    final String path; Uri (String path) { this.path = path; }
    String getEncodedPath () { return path; }
    static String decode (String s) { return s; } static String encode (String s) { return s; } static String encode (String s, String allow) { return s; }
    static class Builder { String path; Builder scheme (String s) { return this; } Builder authority (String a) { return this; }
      Builder encodedPath (String p) { path = p; return this; } Uri build () { return new Uri(path); } }
  }
  static class SimplePathStrategy {
    final String mAuthority = "com.ayx.mgx.provider"; final HashMap<String, File> mRoots = new HashMap<>();
    Map.Entry<String, File> recoverTdlibEntry (File file, String path) { return null; }
    File recoverTdlibRoot (String tag) { return null; }
    /* METHODS */
  }
  static int checks;
  static void check (boolean b, String m) { checks++; if (!b) throw new AssertionError(m); }
  public static void main (String[] args) throws Exception {
    File files = new File(args[0]).getCanonicalFile();
    File vcf = new File(files, "vcf"), backup = new File(files, "vcf_backup");
    vcf.mkdirs(); backup.mkdirs();
    File card = new File(vcf, "a.vcf"), secret = new File(backup, "secret.txt");
    new FileOutputStream(card).close(); new FileOutputStream(secret).close();
    SimplePathStrategy strategy = new SimplePathStrategy(); strategy.mRoots.put("vcf", vcf);
    check(strategy.getFileForUri(new Uri("/vcf/a.vcf")).equals(card), "file inside a root");
    try {
      File escaped = strategy.getFileForUri(new Uri("/vcf/../vcf_backup/secret.txt"));
      throw new AssertionError("a sibling directory with the root's name as prefix was served: " + escaped);
    } catch (SecurityException expected) { checks++; }
    check(strategy.getUriForFile(card).getEncodedPath().equals("vcf/a.vcf"), "URI for a file inside a root");
    try {
      Uri uri = strategy.getUriForFile(secret);
      throw new AssertionError("a sibling directory got a URI under the root: " + uri.getEncodedPath());
    } catch (IllegalArgumentException expected) { checks++; }
    check(SimplePathStrategy.belongsToRoot("/a/b", "/a/b") && SimplePathStrategy.belongsToRoot("/a/b/c", "/a/b") &&
      !SimplePathStrategy.belongsToRoot("/a/bc", "/a/b") && SimplePathStrategy.belongsToRoot("/x", "/"), "segment boundaries");
    System.out.println("file provider boundary: " + checks + " checks passed");
  }
}
'''


def sources(text=None):
    text = text or PROVIDER.read_text(encoding="utf-8")
    methods = "\n".join(method(text, s) for s in (
        "public Uri getUriForFile(File file)", "public File getFileForUri(Uri uri)", "static boolean belongsToRoot ("))
    return HARNESS.replace("/* METHODS */", methods)


class FileProviderBoundaryTest(unittest.TestCase):
    def run_harness(self, source):
        with tempfile.TemporaryDirectory(prefix="file-provider-") as tmp:
            java = Path(tmp) / "ProviderHarness.java"
            java.write_text(source, encoding="utf-8")
            subprocess.run(["javac", "-d", tmp, str(java)], check=True)
            return subprocess.run(["java", "-cp", tmp, "ProviderHarness", str(Path(tmp) / "files")],
                                  capture_output=True, text=True)

    def test_roots_are_whole_path_segments(self):
        result = self.run_harness(sources())
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_negative_string_prefix_escapes_root(self):
        text = PROVIDER.read_text(encoding="utf-8")
        previous = text.replace("if (belongsToRoot(path, rootPath) && (mostSpecific == null", "if (path.startsWith(rootPath) && (mostSpecific == null") \
                       .replace("if (!belongsToRoot(file.getPath(), root.getPath())) {", "if (!file.getPath().startsWith(root.getPath())) {")
        self.assertNotEqual(previous, text)
        result = self.run_harness(sources(previous))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("a sibling directory with the root's name as prefix was served", result.stderr)


if __name__ == "__main__":
    unittest.main()
