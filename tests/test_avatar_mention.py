"""Exercise the production mention replacement method with text/selection doubles.

Android gesture, IME and entity rendering are verified separately on the APK.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/org/thunderdog/challegram/ui/MessagesController.java'


def extract(text):
    start = text.index('  public boolean xgramInsertMention (long userId)')
    depth = 0
    for pos in range(text.index('{', start), len(text)):
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
            if not depth:
                return text[start:pos + 1]
    raise ValueError('Missing method end')


HARNESS = r'''
import java.util.*;
class MentionHarness {
  static class Span { int start,end; Object kind; Span(Object k,int s,int e){kind=k;start=s;end=e;} }
  static class SpannableStringBuilder implements CharSequence {
    final StringBuilder text; final List<Span> spans=new ArrayList<>();
    SpannableStringBuilder(String s){text=new StringBuilder(s);}
    public int length(){return text.length();} public char charAt(int i){return text.charAt(i);}
    public CharSequence subSequence(int a,int b){return text.subSequence(a,b);}
    public String toString(){return text.toString();}
    SpannableStringBuilder append(String s){text.append(s);return this;}
    SpannableStringBuilder append(char c){text.append(c);return this;}
    void insert(int i,String s){text.insert(i,s);}
    void setSpan(Object k,int s,int e,int flags){spans.add(new Span(k,s,e));}
    void replace(int a,int b,SpannableStringBuilder s){text.replace(a,b,s.toString());for(Span span:s.spans)spans.add(new Span(span.kind,a+span.start,a+span.end));}
  }
  static class android {static class text {static class Editable extends SpannableStringBuilder {Editable(String s){super(s);}}}}
  static class org {static class thunderdog {static class challegram {static class util {static class TextSelection {int start,end;TextSelection(int s,int e){start=s;end=e;}}}}}}
  static class Spanned {static final int SPAN_EXCLUSIVE_EXCLUSIVE=33;}
  static class TdApi {static class User {String firstName="Test Name",lastName="",username="user";} static class TextEntityTypeMentionName {long id;TextEntityTypeMentionName(long id){this.id=id;}}}
  static class Td {static String primaryUsername(TdApi.User u){return u.username;}}
  static class TD {static boolean isUserDeleted(TdApi.User u){return false;} static String getUserName(String a,String b){return a.isEmpty()?b:a;}static Object toSpan(Object t){return t;}}
  static class StringUtils {static boolean isEmpty(String s){return s==null||s.isEmpty();}}
  static class InputView {android.text.Editable text;int start,end,cursor;InputView(String s,int a,int b){text=new android.text.Editable(s);start=a;end=b;}android.text.Editable getText(){return text;}org.thunderdog.challegram.util.TextSelection getTextSelection(){return new org.thunderdog.challegram.util.TextSelection(start,end);}void setSelection(int p){cursor=p;}}
  class Cache {TdApi.User user(long id){return user;}}
  class Tdlib {Cache cache(){return new Cache();}}
  final TdApi.User user=new TdApi.User();final Tdlib tdlib=new Tdlib();InputView inputView;boolean keyboard;
  boolean xgramCanInsertMention(){return true;}void showKeyboard(){keyboard=true;}
  PRODUCTION_METHOD
  static void check(boolean v,String m){if(!v)throw new AssertionError(m);}
  static void run(String original,int start,int end,String expected,int cursor,boolean named){
    MentionHarness h=new MentionHarness();h.user.username=named?null:"user";h.inputView=new InputView(original,start,end);
    check(h.xgramInsertMention(42),"mention rejected");check(h.inputView.text.toString().equals(expected),"text: "+h.inputView.text+" expected: "+expected);
    check(h.inputView.cursor==cursor,"caret must follow separator");check(h.keyboard,"keyboard not requested");
    if(named){check(h.inputView.text.spans.size()==1,"name entity missing");Span s=h.inputView.text.spans.get(0);check(h.inputView.text.subSequence(s.start,s.end).toString().equals("Test Name"),"separator included in entity");check(((TdApi.TextEntityTypeMentionName)s.kind).id==42,"wrong identity");}
  }
  public static void main(String[] args){
    run("Keep selected tail",5,13,"Keep @user tail",11,false);
    run("Keep selected\ntail",5,13,"Keep @user\ntail",11,false);
    run("Keep selected\ttail",5,13,"Keep @user\ttail",11,false);
    run("Keep selectedtail",5,13,"Keep @user tail",11,false);
    run("",0,0,"@user ",6,false);
    run("Word",4,4,"Word @user ",11,false);
    run("Wordselected tail",4,12,"Word Test Name tail",15,true);
    run("Keep selected tail",5,13,"Keep Test Name tail",15,true);
    run("Keep selected\ntail",5,13,"Keep Test Name\ntail",15,true);
    run("",0,0,"Test Name ",10,true);
    run("Hello world",5,5,"Hello @user world",12,false);
    run("Wordselected tail",4,12,"Word @user tail",11,false);
    for (char separator : new char[]{'\u00a0','\u2007','\u202f'}) {
      run("Keep selected"+separator+"tail",5,13,"Keep @user"+separator+"tail",11,false);
      run("Keep selected"+separator+"tail",5,13,"Keep Test Name"+separator+"tail",15,true);
      run("Word"+separator+"selected tail",5,13,"Word"+separator+"@user tail",11,false);
    }
    System.out.println("21 production mention text, caret and entity scenarios passed");
  }
}
'''


class AvatarMentionTest(unittest.TestCase):
    def run_method(self, body, success=True, expected_error=None):
        with tempfile.TemporaryDirectory(prefix='avatar-mention-') as temp:
            java = Path(temp) / 'MentionHarness.java'
            java.write_text(HARNESS.replace('PRODUCTION_METHOD', body))
            compiled = subprocess.run(['javac', '-encoding', 'UTF-8', '-d', temp, str(java)], text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run(['java', '-ea', '-cp', temp, 'MentionHarness'], text=True, capture_output=True)
            if success:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, 'Invalid mention behavior was not detected')
                self.assertIn(expected_error, result.stderr)

    def test_existing_separator_caret_and_name_entity(self):
        self.run_method(extract(SOURCE.read_text()))

    def test_duplicate_separator_negative_control(self):
        body = extract(SOURCE.read_text())
        fixed = 'if (!reuseTrailingWhitespace) {'
        self.assertIn(fixed, body)
        self.run_method(body.replace(fixed, 'if (true) {'), success=False, expected_error='AssertionError: text: Keep @user  tail')

    def test_caret_negative_control(self):
        body = extract(SOURCE.read_text())
        fixed = '(reuseTrailingWhitespace ? 1 : 0)'
        self.assertIn(fixed, body)
        self.run_method(body.replace(fixed, '0'), success=False, expected_error='AssertionError: caret must follow separator')


if __name__ == '__main__':
    unittest.main()
