"""Execute the production chat animation policy, including its inherited defaults."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'app/src/main/java/org/thunderdog/challegram'


def method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ChatOpenLatencyTest(unittest.TestCase):
    def run_policy(self, old=False, old_topic_wait=False):
        source = (JAVA / 'ui/MessagesController.java').read_text()
        base = (JAVA / 'navigation/ViewController.java').read_text()
        timeout = 'public long getAsynchronousAnimationTimeout (boolean fastAnimation)'
        policy = '' if old else method(source, timeout)
        if old_topic_wait:
            # The previous policy: forum topics kept the inherited readiness timeout.
            self.assertIn('isInForceTouchMode() ?', policy)
            policy = policy.replace('isInForceTouchMode() ?',
                                    'isInForceTouchMode() || getMessageTopicId() instanceof TdApi.MessageTopicForum ?')
        harness = '''
class TdApi { static class MessageTopicForum {} }
class Parent {
  BASE
}
class Chat extends Parent {
  boolean preview, forceTouch;
  Object topic;
  Object getMessageTopicId() {return topic;}
  Manager manager;
  boolean inPreviewMode() { return preview; }
  boolean isInForceTouchMode() { return forceTouch; }
  ASYNC
  POLICY
}
class Manager {
  boolean empty;
  int messages;
  boolean isTotallyEmpty() { return empty; }
  Manager getAdapter() { return this; }
  int getMessageCount() { return messages; }
}
public class ChatOpenPolicyHarness {
  static int checks;
  static void check(boolean pass, String message) {
    checks++;
    if (!pass) throw new AssertionError(message);
  }
  public static void main(String[] args) {
    Chat c = new Chat();
    check(!c.needAsynchronousAnimation(), "uncreated chat must not wait");
    c.manager = new Manager();
    check(c.needAsynchronousAnimation(), "unloaded chat retains async readiness callback");
    // NavigationController schedules this timeout before attaching the destination.
    // A pending TDLib/blacklist response must not hold ordinary navigation behind it.
    for (int historyDelay : new int[] {20, 250, 500, 30000}) {
      long navigationWait = Math.min(historyDelay, c.getAsynchronousAnimationTimeout(false));
      check(navigationWait == 0, "ordinary navigation waits for history: " + historyDelay);
    }
    check(c.getAsynchronousAnimationTimeout(true) == 2000, "fast preview expansion keeps readiness timeout");
    c.preview = true;
    check(c.getAsynchronousAnimationTimeout(false) == 500, "search/wallpaper preview readiness preserved");
    check(c.getAsynchronousAnimationTimeout(true) == 2000, "fast preview readiness preserved");
    c.preview = false;
    c.forceTouch = true;
    check(c.getAsynchronousAnimationTimeout(false) == 500, "force touch readiness preserved");
    c.forceTouch = false;
    // A forum topic opens like an ordinary chat; its first rows come from a display-only window.
    c.topic = new TdApi.MessageTopicForum();
    for (int historyDelay : new int[] {20, 250, 500, 30000}) {
      long navigationWait = Math.min(historyDelay, c.getAsynchronousAnimationTimeout(false));
      check(navigationWait == 0, "Topic navigation waits for history: " + historyDelay);
    }
    c.manager.messages = 10;
    check(!c.needAsynchronousAnimation(), "loaded chat bypasses scheduling");
    c.manager.messages = 0;
    c.manager.empty = true;
    check(!c.needAsynchronousAnimation(), "known empty chat bypasses scheduling");
    System.out.println(checks + " policy assertions passed");
  }
}
'''.replace('BASE', method(base, timeout)).replace('ASYNC', method(source, 'public boolean needAsynchronousAnimation ()')).replace('POLICY', policy)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'ChatOpenPolicyHarness.java'
            file.write_text(harness)
            subprocess.run(['javac', str(file)], check=True, capture_output=True, text=True)
            return subprocess.run(['java', '-cp', tmp, 'ChatOpenPolicyHarness'], capture_output=True, text=True)

    def test_production_navigation_policy(self):
        result = self.run_policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('16 policy assertions passed', result.stdout)

    def test_topic_readiness_wait_rejected(self):
        result = self.run_policy(old_topic_wait=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Topic navigation waits for history', result.stderr)

    def test_old_history_gate_is_rejected(self):
        result = self.run_policy(old=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ordinary navigation waits for history', result.stderr)


if __name__ == '__main__':
    unittest.main()
