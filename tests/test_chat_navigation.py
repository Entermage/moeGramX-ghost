"""Production-method JVM checks and source wiring checks, NOT an Android E2E test.

The chat manager depends on the entire Android UI. Extract its unchanged method
bodies into a small harness with data/layout doubles; no navigation policy is
reimplemented in the test. Real TDLib requests and RecyclerView rendering still
require a device test.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/src/main/java/org/thunderdog/challegram"
MANAGER = BASE / "component/chat/MessagesManager.java"
LOADER = BASE / "component/chat/MessagesLoader.java"


def block(path, signature):
    source = path.read_text(encoding="utf-8")
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class ChatNavigationTest(unittest.TestCase):
    def test_filtered_centered_anchor_recovery(self):
        method = block(LOADER, "static boolean canContinueFilteredHistory (")
        harness = r'''
public class FilteredAnchorHarness {
  static final int MODE_INITIAL=0,MODE_MORE_TOP=1,MODE_MORE_BOTTOM=2,MODE_REPEAT_INITIAL=3;
  __METHOD__
  static int checks;
  static void check(boolean v,String m) { checks++; if(!v) throw new AssertionError(m); }
  public static void main(String[] args) {
    long anchor=371445L<<20;
    check(canContinueFilteredHistory(MODE_INITIAL,-19,anchor,anchor),"initial cached filtered anchor needs an older window");
    check(canContinueFilteredHistory(MODE_REPEAT_INITIAL,-19,anchor,anchor),"repeat navigation has same recovery");
    check(canContinueFilteredHistory(MODE_INITIAL,-19,anchor,anchor+7),"centered page may contain only newer hidden messages");
    check(!canContinueFilteredHistory(MODE_INITIAL,0,anchor,anchor),"same cursor after normalization must stop");
    check(!canContinueFilteredHistory(MODE_REPEAT_INITIAL,0,anchor,anchor+7),"offset-zero response must move backwards");
    check(!canContinueFilteredHistory(MODE_MORE_TOP,-19,anchor,anchor),"ordinary top paging cannot retry same cursor");
    check(canContinueFilteredHistory(MODE_MORE_TOP,0,anchor,anchor-10),"sparse older IDs advance");
    check(!canContinueFilteredHistory(MODE_MORE_BOTTOM,-99,anchor,anchor),"bottom paging cannot repeat anchor");
    check(canContinueFilteredHistory(MODE_MORE_BOTTOM,-99,anchor,anchor+10),"sparse newer IDs advance");
    check(!canContinueFilteredHistory(MODE_MORE_BOTTOM,-99,0,anchor),"bottom requires concrete anchor");
    check(!canContinueFilteredHistory(MODE_INITIAL,-19,anchor,0),"no raw message is not recoverable by retry");
    System.out.println("Filtered history anchor: "+checks+" production-method checks passed");
  }
}
'''.replace("__METHOD__", method)
        with tempfile.TemporaryDirectory(prefix="filtered-anchor-test-") as directory:
            java = Path(directory) / "FilteredAnchorHarness.java"
            java.write_text(harness, encoding="utf-8")
            subprocess.run(["javac", "-d", directory, str(java)], check=True)
            subprocess.run(["java", "-cp", directory, "FilteredAnchorHarness"], check=True)
        process = block(LOADER, "private void processMessages (")
        self.assertIn("canContinueFilteredHistory(loadingMode, lastOffset, previousRawCursor, continuationRawMessage.id)", process)
        self.assertIn("continueTowardBottom ? FILTERED_PAGE_BOTTOM_OFFSET : 0", process)

    def test_production_bookmarks_and_default_anchor(self):
        methods = "\n".join(block(MANAGER, signature) for signature in (
            "public static boolean canGoUnread (",
            "public static final class DefaultAnchor {",
            "public static DefaultAnchor resolveDefaultAnchor (",
            "public static MessageId resolveUnreadAnchor (",
            "private void saveScrollPosition ()",
        ))
        harness = r'''
import java.util.*;
public class ChatAnchorHarness {
  @interface Nullable {}
  static final int CHATS_THRESHOLD=1, HIGHLIGHT_MODE_NONE=0, HIGHLIGHT_MODE_UNREAD=2,
    HIGHLIGHT_MODE_POSITION_RESTORE=3;
  static class MessageId {
    static final long MIN_VALID_ID=1, MAX_VALID_ID=Long.MAX_VALUE;
    long chatId, id; long[] others;
    MessageId(long c,long i) { chatId=c; id=i; }
    MessageId(long c,long i,long[] o) { this(c,i); others=o; }
    long getMessageId() { return id; }
  }
  static class ChatId { static boolean isMultiChat(long id) { return id<0; } }
  static class TdApi {
    static class MessageTopic {}
    static class Message { long id=200; boolean isOutgoing; }
    static class Chat {
      long id=-1002462267293L, lastReadInboxMessageId=100, lastReadOutboxMessageId=0;
      int unreadCount=19; Message lastMessage=new Message();
    }
  }
  static class ThreadInfo {
    TdApi.MessageTopic topic=new TdApi.MessageTopic();
    long getChatId() { return -1002462267293L; }
    long getLastReadInboxMessageId() { return 110; }
    boolean hasUnreadMessages(TdApi.Chat c) { return true; }
    TdApi.MessageTopic getMessageTopicId() { return topic; }
  }
  static class Settings {
    static Settings INSTANCE=new Settings();
    static Settings instance() { return INSTANCE; }
    SavedMessageId saved; int account; long chat; TdApi.MessageTopic topic;
    SavedMessageId getScrollMessageId(int a,long c,TdApi.MessageTopic t) {
      account=a; chat=c; topic=t; return saved;
    }
    void setScrollMessageId(int a,long c,TdApi.MessageTopic t,SavedMessageId s) {
      account=a; chat=c; topic=t; saved=s;
    }
    static class SavedMessageId {
      MessageId id; int offsetPixels; long[] returnToMessageIds; boolean readFully; long topEndMessageId;
      SavedMessageId(MessageId i,int o,long[] r,boolean f,long t) {
        id=i; offsetPixels=o; returnToMessageIds=r; readFully=f; topEndMessageId=t;
      }
    }
  }
  static class Tdlib { int id() { return 7; } }
  static class TGMessage {
    long id; boolean sponsored;
    TGMessage(long i) { id=i; }
    long getChatId() { return -1002462267293L; }
    long getBiggestId() { return id; }
    long getSmallestId() { return id-1; }
    long[] getOtherMessageIds(long id) { return new long[] {id-1}; }
    boolean isSponsoredMessage() { return sponsored; }
    int getExtraPadding() { return 3; }
    MessageId toMessageId() { return new MessageId(getChatId(),id); }
  }
  static class RecyclerView { static final int NO_POSITION=-1; }
  static class View {
    int offset;
    Object getParent() { return this; }
    int getMeasuredHeight() { return 40; }
  }
  static class Layout {
    int first; View view=new View();
    int findFirstVisibleItemPosition() { return first; }
    int findLastVisibleItemPosition() { return first; }
    View findViewByPosition(int index) { return view; }
  }
  static class MessagesHolder { static boolean isMessageType(int type) { return true; } }
  static class Adapter {
    TGMessage message=new TGMessage(150), active=message;
    TGMessage getMessage(int index) { return index<0 ? null : message; }
    TGMessage getBottomActiveMessage() { return active; }
    int getItemViewType(int index) { return 1; }
    int indexOfMessageContainer(MessageId id) { return 1; }
  }
  static class Loader {
    boolean moreBottom, moreTop=true; TdApi.MessageTopic topic;
    long getChatId() { return -1002462267293L; }
    TdApi.MessageTopic getMessageTopicId() { return topic; }
    boolean canLoadBottom() { return moreBottom; }
    boolean canLoadTop() { return moreTop; }
  }
  static class Pinned { void ensureMessageAvailability(long id) {} }
  Tdlib tdlib=new Tdlib(); Layout manager=new Layout(); Adapter adapter=new Adapter(); Loader loader=new Loader();
  Pinned pinnedMessages; long[] returnToMessageIds={90}; boolean isFocused=true, atBottom=true;
  boolean canRead() { return true; }
  int getExtraScrollSpacing() { return 0; }
  int calculateOffsetInPixels(View v,int padding) { return v.offset+padding; }
  boolean isTotallyEmpty() { return false; }
  boolean isAtVeryBottom() { return atBottom; }
  int getActiveMessageCount() { return 1; }
  __METHODS__
  static int checks;
  static void check(boolean value,String reason) { checks++; if(!value) throw new AssertionError(reason); }
  public static void main(String[] args) {
    ChatAnchorHarness h=new ChatAnchorHarness();
    Settings s=Settings.instance(); TdApi.Chat chat=new TdApi.Chat();
    DefaultAnchor anchor=resolveDefaultAnchor(7,chat,null);
    check(anchor.highlightMode==HIGHLIGHT_MODE_UNREAD && anchor.messageId.id==100,"raw cursor is an unread search boundary");
    h.manager.view.offset=-3;
    h.saveScrollPosition();
    check(s.saved.id.id==150 && s.saved.offsetPixels==0,"bottom bookmark must not be erased at zero offset");
    check(s.saved.readFully,"visible bottom + confirmed raw end is fully read despite hidden raw tail 200");
    check(s.topic==null && s.account==7 && s.chat==chat.id,"merged forum uses account/chat scope, not individual topic");
    check(s.saved.id.others[0]==149 && s.saved.returnToMessageIds[0]==90,"album IDs and return stack preserved");
    check(resolveDefaultAnchor(7,chat,null).highlightMode==HIGHLIGHT_MODE_UNREAD,"new unread takes precedence after bottom");
    chat.unreadCount=0;
    anchor=resolveDefaultAnchor(7,chat,null);
    check(anchor.highlightMode==HIGHLIGHT_MODE_POSITION_RESTORE && anchor.messageId.id==150,"no unread restores concrete bottom bookmark");
    h.loader.moreBottom=true;
    h.manager.view.offset=23;
    h.saveScrollPosition();
    check(!s.saved.readFully && s.saved.offsetPixels==26,"bottom of loaded window is not confirmed history end; pixel offset retained");
    chat.unreadCount=19;
    check(resolveDefaultAnchor(7,chat,null).messageId.id==150,"unfinished bookmark beats raw unread boundary");
    h.loader.moreBottom=false; h.atBottom=false; h.saveScrollPosition();
    check(!s.saved.readFully,"being in the final loaded page is not being at its bottom");
    h.atBottom=true; h.adapter.message.sponsored=true; h.adapter.active=new TGMessage(170); h.saveScrollPosition();
    check(s.saved.id.id==170,"sponsored row is never saved as the message bookmark");
    s.saved=null;
    ThreadInfo thread=new ThreadInfo();
    anchor=resolveDefaultAnchor(7,chat,thread);
    check(s.topic==thread.topic && anchor.messageId.id==110,"real comment thread retains independent scope");
    chat.lastMessage.isOutgoing=true;
    check(resolveDefaultAnchor(7,chat,null).highlightMode==HIGHLIGHT_MODE_NONE,"existing outgoing-last policy unchanged");
    chat.id=42; chat.lastMessage.isOutgoing=false; chat.lastReadOutboxMessageId=130;
    check(resolveUnreadAnchor(chat,null).id==130,"existing private outbox cursor rule unchanged");
    check(resolveDefaultAnchor(7,null,null).messageId==null,"null chat has no anchor");
    System.out.println("Chat anchors/bookmarks: "+checks+" production-method checks passed (UI doubles)");
  }
}
'''.replace("__METHODS__", methods)
        with tempfile.TemporaryDirectory(prefix="chat-anchor-test-") as directory:
            java = Path(directory) / "ChatAnchorHarness.java"
            java.write_text(harness, encoding="utf-8")
            subprocess.run(["javac", "-d", directory, str(java)], check=True)
            subprocess.run(["java", "-cp", directory, "ChatAnchorHarness"], check=True)

    def test_default_entry_points_and_explicit_links(self):
        opening = block(BASE / "ui/ChatsController.java", "private void openChat (TdApi.Chat chat)")
        self.assertNotIn("highlightMessage(", opening)
        self.assertIn("pickerDelegate.modifyChatOpenParams(params)", opening)
        ui = (BASE / "telegram/TdlibUi.java").read_text()
        self.assertIn("if (params != null && params.highlightSet)", ui)
        self.assertIn("MessagesManager.resolveDefaultAnchor(tdlib.id(), chat, messageThread)", ui)
        controller = (BASE / "ui/MessagesController.java").read_text()
        self.assertEqual(controller.count("MessagesManager.resolveDefaultAnchor(tdlib.id(), chat, messageThread)"), 2)
        self.assertNotIn("canUseRawUnreadAnchor", controller)
        highlight = block(MANAGER, "public void highlightMessage (MessageId messageId, int highlightMode,")
        self.assertIn("highlightMode == HIGHLIGHT_MODE_UNREAD || highlightMode == HIGHLIGHT_MODE_UNREAD_NEXT", highlight)

    def test_cancellation_and_bounded_request_wiring(self):
        manager = MANAGER.read_text()
        self.assertIn("loader.cancelUnreadNavigation();", block(MANAGER, "private void onBlur ()"))
        self.assertIn("loader.resumeUnreadNavigation();", block(MANAGER, "private void onFocus ()"))
        self.assertIn("loader.cancelUnreadNavigation();", block(MANAGER, "public void highlightMessage (MessageId messageId, int highlightMode,"))
        drag = manager[manager.index("if (newState == RecyclerView.SCROLL_STATE_DRAGGING)"):]
        self.assertLess(drag.index("loader.cancelUnreadNavigation();"), drag.index("wasScrollByUser = true"))
        cancel = block(LOADER, "public void cancelUnreadNavigation ()")
        self.assertIn("contextId++", cancel)
        self.assertIn("lastHandler = null", cancel)
        self.assertIn("canLoadBottom = unreadPreviousCanLoadBottom", cancel)
        self.assertIn("resumeUnreadOnFocus = manager.getAdapter().getMessageCount() == 0", cancel)
        page = block(LOADER, "private @Nullable TdApi.Message[] prepareVisibleUnreadPageLocked (")
        self.assertIn("contextId != currentContextId || visibleUnreadAnchor != navigation", page)
        self.assertIn("manager.getUserScrollActionsCount() != unreadNavigationScrollActions", page)
        self.assertIn("-(VisibleUnreadAnchor.PAGE_LIMIT - 1)", page)
        self.assertIn("navigation.delayMillis()", page)
        self.assertNotIn("displayMessages", page)
        load_more = block(LOADER, "private boolean loadMore (boolean fromTop, int count, boolean onlyLocal)")
        self.assertIn("unreadNavigationStopped && manager.getUserScrollActionsCount() == unreadNavigationScrollActions", load_more)

    def test_resolved_target_not_advanced_again_or_cleared(self):
        process = block(LOADER, "private void processMessages (")
        self.assertIn("if (!hasResolvedUnreadTarget && scrollItemIndex > 0)", process)
        self.assertIn("if (!hasResolvedUnreadTarget && unreadBadged != null", process)
        self.assertIn("!unreadNavigationResult && filteredOnlyPage", process)
        self.assertIn("if (!stopUnreadPrefetch) manager.ensureContentHeight();", process)
        unavailable = block(MANAGER, "public void onUnreadAnchorUnavailable ()")
        self.assertNotIn("reset", unavailable)
        self.assertNotIn("displayMessages", unavailable)
        self.assertIn("notifyDataSetChanged", unavailable)


if __name__ == "__main__":
    unittest.main()
