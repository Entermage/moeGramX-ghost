"""Execute production preview lifecycle/visibility methods; Android E2E is separate."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'app/src/main/java/org/thunderdog/challegram'
BAR = BASE / 'component/chat/PinnedMessagesBar.java'
CHAT = BASE / 'ui/MessagesController.java'
ADAPTER = BASE / 'ui/SettingsAdapter.java'


def harness():
    bar = '\n'.join(block(BAR, signature) for signature in (
        'private void clearMessageList ()',
        'public void setMessageList (@Nullable MessageListManager messageList)',
        'public void setStaticMessageList (@Nullable List<Entry> entries, int scrollToPosition)',
    ))
    adapter = '\n'.join(block(ADAPTER, signature) for signature in (
        'public void setNoEmptyProgress ()', 'public int getItemCount ()',
    ))
    chat = '\n'.join(block(CHAT, signature) for signature in (
        'private float getReplyOffset ()', 'private void updateReplyBarViewVisibility ()',
        'private void updateReplyView ()',
    ))
    initialize = block(BAR, 'public void initialize (')
    setup = re.search(r'(messagesAdapter\.setNoEmptyProgress\(\);)\s*recyclerView\.setAdapter', initialize)
    if not setup:
        raise AssertionError('Empty preview must opt out before attaching the adapter')
    return r'''
import java.util.*;
public class IdleRenderHarness {
  @interface Nullable { }
  static int checks;
  static void check(boolean value, String message) {
    checks++; if (!value) throw new AssertionError(message);
  }
  static class TdApi { static class Message { } }
  static class Entry {
    int destroyed, subscribed;
    void performDestroy() { destroyed++; }
    void subscribeToUpdates() { subscribed++; }
  }
  static class ListItem { }
  static class MessageListManager extends ArrayList<TdApi.Message> {
    int adds, removes, loads;
    int getTotalCount() { return size(); }
    int getCount() { return size(); }
    Object tdlib() { return null; }
    void addChangeListener(Object l) { adds++; }
    void removeChangeListener(Object l) { removes++; }
    void loadInitialChunk(Object l) { loads++; }
  }
  static class SettingsAdapter {
    boolean noEmptyProgress;
    ArrayList<ListItem> items = new ArrayList<>();
    __ADAPTER__
    void setItems(List<ListItem> next, boolean checked) { items.clear(); items.addAll(next); }
    void setItems(ListItem[] next, boolean checked) { setItems(Arrays.asList(next), checked); }
  }
  static class LinearLayoutManager { void scrollToPositionWithOffset(int p, int off) { } }
  static class RecyclerView {
    static final int NO_POSITION = -1;
    Object getLayoutManager() { return new LinearLayoutManager(); }
  }
  static class Animator {
    float value;
    void setValue(boolean value, boolean animated) { this.value = value ? 1 : 0; }
    void forceFactor(float value) { this.value = value; }
    float getFloatValue() { return value; }
  }
  static class Bar {
    List<Entry> staticList;
    MessageListManager messageList;
    int focusIndex = RecyclerView.NO_POSITION;
    boolean needsClear;
    SettingsAdapter messagesAdapter = new SettingsAdapter();
    Animator canExpand = new Animator(), countAnimator = new Animator();
    RecyclerView recyclerView = new RecyclerView();
    Bar(boolean legacy) { if (!legacy) { __SETUP__ } }
    void collapse(boolean animated) { }
    ListItem itemOf(Object tdlib, TdApi.Message m) { return new ListItem(); }
    ListItem itemOf(Entry e) { return new ListItem(); }
    __BAR__
  }
  static class View {
    static final int VISIBLE = 0, INVISIBLE = 4, GONE = 8;
    int visibility = VISIBLE;
    float y;
    LayoutParams params = new LayoutParams();
    int getVisibility() { return visibility; }
    void setVisibility(int v) { visibility = v; }
    void setTranslationY(float y) { this.y = y; }
    LayoutParams getLayoutParams() { return params; }
  }
  static class LayoutParams { int height = 72; }
  static class Chat {
    View bottomWrap = new View(), replyBarView = new View();
    View messagesView = new View(), bottomShadowView = new View();
    Animator replyBarVisible = new Animator();
    float search, keyboard;
    float getSearchTransformFactor() { return search; }
    float getAttachedFilesOffset() { return 0; }
    float getKeyboardOffset() { return keyboard; }
    void checkScrollButtonOffsets() { }
    void onMessagesFrameChanged() { }
    __CHAT__
  }
  static void empty(boolean legacy) {
    Bar b = new Bar(legacy);
    check(b.messagesAdapter.getItemCount() == 0, "Empty preview must not create a spinner");
    b.setMessageList(null);
    check(b.messagesAdapter.getItemCount() == 0, "Repeated empty reset stays idle");
  }
  static void lifecycle() {
    Bar b = new Bar(false);
    Entry reply = new Entry();
    b.setStaticMessageList(Collections.singletonList(reply), -1);
    check(b.messagesAdapter.getItemCount() == 1 && reply.subscribed == 1, "Reply must still display");
    b.needsClear = true;
    b.setMessageList(null);
    check(b.messagesAdapter.getItemCount() == 0 && b.staticList == null && reply.destroyed == 1,
      "Closing static reply must release preview content");
    check(!b.needsClear && b.focusIndex == -1, "Cleared source must drop removal state");
    b.setMessageList(null);
    check(reply.destroyed == 1, "Repeated reset does not destroy twice");
    Entry link = new Entry();
    b.setStaticMessageList(Collections.singletonList(link), -1);
    b.setStaticMessageList(Collections.emptyList(), -1);
    check(link.destroyed == 1 && b.messagesAdapter.getItemCount() == 0, "Empty link preview clears static source");
    MessageListManager list = new MessageListManager(); list.add(new TdApi.Message());
    b.setMessageList(list); b.setMessageList(list);
    check(list.adds == 1 && list.loads == 1 && b.messagesAdapter.getItemCount() == 1,
      "Existing pinned source is not resubscribed or reloaded");
    Entry next = new Entry(); b.needsClear = true;
    b.setStaticMessageList(Collections.singletonList(next), -1);
    check(list.removes == 1 && !b.needsClear, "Switch to static preview releases old list state");
    b.setMessageList(list);
    check(next.destroyed == 1 && list.adds == 2 && list.loads == 2, "Live pinned list can resume");
    b.setMessageList(null);
    check(list.removes == 2 && b.messagesAdapter.getItemCount() == 0, "Clearing live list stays idle");
  }
  static void visibility() {
    Chat c = new Chat(); c.updateReplyView();
    check(c.replyBarView.visibility == View.INVISIBLE, "Collapsed reply must stop drawing");
    for (float f : new float[]{.01f, .5f, 1f}) {
      c.replyBarVisible.value = f; c.updateReplyView();
      check(c.replyBarView.visibility == View.VISIBLE && c.replyBarView.y == -72*f,
        "Opening animation retains partial and full reply");
    }
    c.search = 1; c.updateReplyView();
    check(c.replyBarView.visibility == View.INVISIBLE, "Search-covered reply must stop drawing");
    c.search = 0; c.keyboard = 400; c.updateReplyView();
    check(c.replyBarView.visibility == View.VISIBLE && c.replyBarView.y == -472,
      "Keyboard still moves active reply");
    c.bottomWrap.visibility = View.GONE; c.updateReplyView();
    check(c.replyBarView.visibility == View.GONE, "Hidden composer hides reply");
    c.bottomWrap.visibility = View.VISIBLE; c.updateReplyBarViewVisibility();
    check(c.replyBarView.visibility == View.VISIBLE, "Restored composer reveals active reply");
    c.replyBarVisible.value = 0; c.updateReplyView();
    check(c.replyBarView.visibility == View.INVISIBLE, "Finished dismissal becomes idle");
    c.replyBarView = null; c.updateReplyView();
  }
  public static void main(String[] args) {
    if (args[0].equals("empty")) empty(args.length > 1);
    if (args[0].equals("lifecycle")) lifecycle();
    if (args[0].equals("visibility")) visibility();
    System.out.println(checks + " production checks passed");
  }
}
'''.replace('__ADAPTER__', adapter).replace('__BAR__', bar).replace('__CHAT__', chat).replace('__SETUP__', setup[1])


class ChatIdleRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='chat-idle-')
        cls.source = harness()
        cls.compile(cls.source)

    @classmethod
    def compile(cls, source):
        file = Path(cls.tmp.name) / 'IdleRenderHarness.java'
        file.write_text(source)
        subprocess.run(['javac', '-encoding', 'UTF-8', '-d', cls.tmp.name, str(file)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, *args):
        return subprocess.run(['java', '-cp', self.tmp.name, 'IdleRenderHarness', *args], capture_output=True, text=True)

    def test_empty_preview_and_legacy_negative_control(self):
        self.assertEqual(self.run_case('empty').returncode, 0)
        old = self.run_case('empty', 'legacy')
        self.assertNotEqual(old.returncode, 0)
        self.assertIn('must not create a spinner', old.stderr)

    def test_preview_cleanup_and_legacy_negative_control(self):
        result = self.run_case('lifecycle')
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            self.compile(self.source.replace('this.messageList == messageList && this.staticList == null', 'this.messageList == messageList'))
            old = self.run_case('lifecycle')
            self.assertNotEqual(old.returncode, 0)
            self.assertIn('must release preview content', old.stderr)
        finally:
            self.compile(self.source)

    def test_reply_visibility_and_legacy_negative_control(self):
        result = self.run_case('visibility')
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            self.compile(self.source.replace('      updateReplyBarViewVisibility();', ''))
            old = self.run_case('visibility')
            self.assertNotEqual(old.returncode, 0)
            self.assertIn('must stop drawing', old.stderr)
        finally:
            self.compile(self.source)


if __name__ == '__main__':
    unittest.main()
