"""Small production-method check for programmatic search IME requests.

Native EditText touch/focus is unchanged and remains an Android E2E check.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/"app/src/main/java/org/thunderdog/challegram"
PAGE=JAVA/"ui/EmojiStatusSelectorEmojiPage.java"
BASE=JAVA/"navigation/ViewController.java"


def source_for(broken=None):
    page="\n".join(block(PAGE,s) for s in (
        "private void closeEmojiSelectMode (", "protected void updateSearchMode (",
        "protected void onSearchInputChanged (", "public void onEnterEmoji (",
    ))
    base="\n".join(block(BASE,s) for s in (
        "protected void updateSearchMode (boolean inSearch, boolean needUpdateKeyboard)",
        "protected void updateSearchMode (boolean inSearch)",
    ))
    if broken=="transition":page=page.replace("!inSearch && needUpdateKeyboard", "needUpdateKeyboard")
    if broken=="clear":page=page.replace("emojiSearchRequest = null;", "emojiSearchRequest = null; Keyboard.show(getSearchHeaderView(headerView).editView());")
    return TEMPLATE.replace("/* PAGE */",page).replace("/* BASE */",base)


TEMPLATE=r"""
public class EmojiStatusKeyboardHarness {
  static class EditText {boolean enabled=true;void setEnabled(boolean b){enabled=b;}}
  static class SearchHeader {EditText edit=new EditText();EditText editView(){return edit;}}
  static class Keyboard {static int shown,hidden;static void show(Object v){shown++;}static void hide(Object v){hidden++;}}
  static class StringUtils {static boolean isEmpty(String s){return s==null||s.isEmpty();}}
  static class BoolAnimator {boolean value;void setValue(boolean v,boolean animated){value=v;}}
  static class SearchController {String input,emoji;void search(String i,String e){input=i;emoji=e;}}
  static class Base {
    Object cachedLockFocusView,lockFocusView=new Object();SearchHeader searchHeaderView=new SearchHeader();
    protected void onSearchInputChanged(String input){}
    /* BASE */
  }
  static class Header {
    Page page;boolean requestedKeyboard;Runnable animationEnd;
    Header(Page p){page=p;}
    void openSearchMode(){openSearchMode(true,true);}
    void openSearchMode(boolean animated,boolean keyboard){requestedKeyboard=keyboard;animationEnd=()->page.updateSearchMode(true,keyboard);}
    void finishAnimation(){animationEnd.run();}
  }
  static class Page extends Base {
    boolean inEmojiSelectMode=true;String currentSearchInput,emojiSearchRequest;
    BoolAnimator emojiSelectorVisibility=new BoolAnimator(),emojiSelectorButtonsVisibility=new BoolAnimator(),searchModeVisibility=new BoolAnimator(),searchFieldIsNotEmpty=new BoolAnimator();
    Header headerView=new Header(this);SearchController emojiCustomListController=new SearchController();
    SearchHeader getSearchHeaderView(Header h){return searchHeaderView;}
    void setSearchInput(String text){onSearchInputChanged(text);}
    /* PAGE */
  }
  static int checks;
  static void check(boolean b,String message){checks++;if(!b)throw new AssertionError(message);}
  public static void main(String[] args){
    Page p=new Page();p.closeEmojiSelectMode();
    check(!p.inEmojiSelectMode&&!p.headerView.requestedKeyboard,"cancelling filter exposes search without requesting IME");
    check(Keyboard.shown==0,"cancel must not immediately open keyboard");
    p.headerView.finishAnimation();check(Keyboard.shown==0,"delayed cancel animation must not open keyboard");
    p.updateSearchMode(true,true);p.updateSearchMode(true);
    check(Keyboard.shown==0,"delayed generic header callbacks cannot open keyboard");
    p.onEnterEmoji("test-emoji");p.headerView.finishAnimation();
    check(Keyboard.shown==0&&!p.searchHeaderView.edit.enabled,"choosing a filter does not open keyboard");
    check("test-emoji".equals(p.emojiCustomListController.emoji),"emoji filter reaches search controller");
    p.onSearchInputChanged("");
    check(Keyboard.shown==0,"clearing emoji filter must not open keyboard");
    check(p.emojiSearchRequest==null&&p.searchHeaderView.edit.enabled,"clearing filter restores enabled text input");
    check(p.emojiCustomListController.emoji==null&&"".equals(p.emojiCustomListController.input),"clearing filter updates results");
    p.onSearchInputChanged("word");p.onSearchInputChanged("");check(Keyboard.shown==0,"ordinary query clearing must not open keyboard");
    int hides=Keyboard.hidden;p.updateSearchMode(false,false);check(Keyboard.hidden==hides,"exit preserves false keyboard-update flag");
    p.updateSearchMode(false,true);check(Keyboard.hidden==hides+1,"exit preserves requested keyboard hide");
    Base other=new Base();other.updateSearchMode(true,true);check(Keyboard.shown==1,"other controllers retain default keyboard behavior");
    System.out.println(checks+" production search keyboard checks passed");
  }
}
"""


def run_harness(broken=None):
    with tempfile.TemporaryDirectory(prefix="emoji-status-keyboard-") as directory:
        source=Path(directory)/"EmojiStatusKeyboardHarness.java"
        source.write_text(source_for(broken),encoding="utf-8")
        subprocess.run(["javac","-d",directory,str(source)],check=True)
        return subprocess.run(["java","-cp",directory,"EmojiStatusKeyboardHarness"],capture_output=True,text=True,timeout=15)


class EmojiStatusKeyboardTest(unittest.TestCase):
    def test_transitions_and_filter_clear_do_not_show_but_exit_can_hide(self):
        result=run_harness()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("13 production search keyboard checks passed",result.stdout)

    def test_negative_controls_detect_delayed_and_clear_keyboard_requests(self):
        for broken,message in (("transition","delayed generic header"),("clear","clearing emoji filter")):
            with self.subTest(broken=broken):
                result=run_harness(broken)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(message,result.stderr)


if __name__=="__main__":unittest.main()
