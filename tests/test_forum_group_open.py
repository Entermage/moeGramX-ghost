"""Run the real forum-list navigation policy with delayed/failed initial metadata."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/moe/kirao/mgx/topics/ForumTopicsController.java'
BASE = ROOT / 'app/src/main/java/org/thunderdog/challegram/navigation/ViewController.java'


def method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ForumGroupOpenTest(unittest.TestCase):
    def run_policy(self, old=False):
        policy = method(SOURCE.read_text(), 'public boolean needAsynchronousAnimation ()')
        if old:
            policy = 'public boolean needAsynchronousAnimation () { return !ensureList().isLoaded(); }'
        timeout = method(BASE.read_text(), 'public long getAsynchronousAnimationTimeout (boolean fastAnimation)')
        harness = r"""
class TopicList {
  boolean loaded;
  boolean isLoaded() { return loaded; }
}
class Controller {
  final TopicList list = new TopicList();
  int ensureCalls;
  TopicList ensureList() { ensureCalls++; return list; }
  POLICY
  TIMEOUT
}
public class ForumGroupOpenHarness {
  static int checks;
  static void check(boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }
  public static void main(String[] args) {
    Controller c = new Controller();
    // Every new controller may have an uncached list, including after returning
    // to the main chat list. Failed or queued requests also remain not-loaded.
    for (boolean loaded : new boolean[] {false, true, false}) {
      c.list.loaded = loaded;
      for (boolean fast : new boolean[] {false, true}) {
        for (int responseDelay : new int[] {20, 250, 500, 30000}) {
          long wait = c.needAsynchronousAnimation() ?
              Math.min(responseDelay, c.getAsynchronousAnimationTimeout(fast)) : 0;
          check(wait == 0, "forum group navigation waited for metadata: " + responseDelay);
        }
      }
    }
    check(c.ensureCalls == 0, "checking navigation readiness must not start network work");
    System.out.println(checks + " forum group opening assertions passed");
  }
}
""".replace('POLICY', policy).replace('TIMEOUT', timeout)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ForumGroupOpenHarness.java'
            path.write_text(harness)
            subprocess.run(['javac', str(path)], check=True, capture_output=True, text=True)
            return subprocess.run(['java', '-cp', tmp, 'ForumGroupOpenHarness'], capture_output=True, text=True)

    def test_pending_or_failed_metadata_does_not_delay_navigation(self):
        result = self.run_policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('25 forum group opening assertions passed', result.stdout)

    def test_old_first_page_gate_is_rejected(self):
        result = self.run_policy(old=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('forum group navigation waited for metadata', result.stderr)


if __name__ == '__main__':
    unittest.main()
