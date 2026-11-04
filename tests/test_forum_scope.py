"""Run production cursor and topic-membership rules with malformed/stale TDLib pages."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'app/src/main/java/moe/kirao/mgx/topics'


def method(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


HARNESS = '''
public class ScopeHarness {
  static final int GENERAL_TOPIC_ID = 1;
  static class TdApi {
    static class Message {Object topicId; Message(Object t){topicId=t;}}
    static class MessageTopicForum {int forumTopicId; MessageTopicForum(int id){forumTopicId=id;}}
  }
  METHODS
  static int checks;
  static void check(boolean ok, String detail){checks++;if(!ok)throw new AssertionError(detail);}
  public static void main(String[] args){
    check(!endOfPage(3,3,50,0,0,0,20,200,3), "a short page with a valid cursor must continue");
    check(endOfPage(0,3,50,20,200,3,21,201,4), "empty pages terminate");
    check(endOfPage(10,13,50,20,200,3,20,200,3), "repeated cursor cannot create a loading loop");
    check(endOfPage(10,13,50,20,200,3,0,0,0), "no cursor terminates");
    check(endOfPage(10,50,50,20,200,3,21,201,4), "known total reached");
    check(!endOfPage(10,13,0,20,200,3,21,201,4), "unknown total does not stop pagination");
    int pages=0, oldDate=0;long oldMessage=0;int oldTopic=0;
    while(pages<100){pages++;boolean stop=endOfPage(20,20,999,oldDate,oldMessage,oldTopic,20,200,3);oldDate=20;oldMessage=200;oldTopic=3;if(stop)break;}
    check(pages==2, "stale server cursor is bounded");
    check(isInTopic(new TdApi.Message(null),1), "unthreaded forum messages belong to General");
    check(!isInTopic(new TdApi.Message(null),9), "unthreaded messages must not leak into another topic");
    for(int id=1;id<=20;id++)for(int selected=1;selected<=20;selected++)
      check(isInTopic(new TdApi.Message(new TdApi.MessageTopicForum(id)),selected)==(id==selected), "exact topic scope");
    check(!isInTopic(new TdApi.Message(new Object()),1), "other thread types must not become General");
    System.out.println("checks="+checks);
  }
}
'''


class ForumScopeTest(unittest.TestCase):
    def run_harness(self, mutation=None):
        page = method((PACKAGE / 'ForumTopicList.java').read_text(), 'static boolean endOfPage (')
        scope = method((PACKAGE / 'XgramForums.java').read_text(), 'public static boolean isInTopic (')
        code = HARNESS.replace('METHODS', page + '\n' + scope)
        if mutation:
            code = mutation(code)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ScopeHarness.java'
            path.write_text(code)
            subprocess.run(['javac', str(path)], check=True, capture_output=True, text=True)
            return subprocess.run(['java', '-cp', tmp, 'ScopeHarness'], capture_output=True, text=True)

    def test_cursor_and_membership(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('checks=410', result.stdout)

    def test_negative_repeated_cursor(self):
        result = self.run_harness(lambda s: s.replace(
            '(oldDate == nextDate && oldMessage == nextMessage && oldTopic == nextTopic)', 'false'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('repeated cursor', result.stderr)

    def test_negative_cross_topic_leak(self):
        result = self.run_harness(lambda s: s.replace(
            'return message.topicId == null && forumTopicId == GENERAL_TOPIC_ID;',
            'return message.topicId == null;'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must not leak', result.stderr)


if __name__ == '__main__':
    unittest.main()
