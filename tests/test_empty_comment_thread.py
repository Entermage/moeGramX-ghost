"""Execute production comment anchors/load entry methods with TDLib/UI doubles.

This verifies request/selection boundaries; it is not an Android UI or Telegram
network test. The exact zero-comment post must also be opened in the app.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_chat_navigation import BASE, LOADER, MANAGER, block

ROOT = Path(__file__).resolve().parents[1]
THREAD = BASE / 'data/ThreadInfo.java'


class EmptyCommentThreadTest(unittest.TestCase):
    def test_production_default_thread_entry(self):
        anchors = '\n'.join(block(MANAGER, signature) for signature in (
            'public static boolean canGoUnread (',
            'public static final class DefaultAnchor {',
            'public static DefaultAnchor resolveDefaultAnchor (',
            'public static MessageId resolveUnreadAnchor (',
        ))
        metadata = '\n'.join(block(THREAD, signature) for signature in (
            'public boolean hasUnreadMessages (@Nullable TdApi.Chat chat)',
            'public boolean hasUnreadMessages (long lastGlobalReadInboxMessageId)',
            'public int getUnreadMessageCount ()',
            'public int getReplyCount ()',
            'public long getChatId ()',
            'public long getLastReadInboxMessageId ()',
            'public long getNewestMessageId ()',
            'public @Nullable TdApi.Message getNewestMessage ()',
            'public static @Nullable TdApi.Message getNewestMessage (@Nullable TdApi.MessageThreadInfo threadInfo)',
        ))
        entries = '\n'.join(block(LOADER, signature) for signature in (
            'public void loadFromStart (MessageId startMessageId)',
            'public void loadFromMessage (MessageId messageId, final int highlightMode, boolean force)',
        ))
        harness = r'''
import org.thunderdog.challegram.component.chat.VisibleUnreadAnchor;
public class EmptyCommentHarness {
  @interface Nullable {}
  static final int CHATS_THRESHOLD=1, HIGHLIGHT_MODE_NONE=0, HIGHLIGHT_MODE_UNREAD=2,
    HIGHLIGHT_MODE_POSITION_RESTORE=3;
  static class MessageId {
    static final long MIN_VALID_ID=1, MAX_VALID_ID=Long.MAX_VALUE;
    long chatId,id;
    MessageId(long c,long i) { chatId=c; id=i; }
    long getChatId() { return chatId; }
    long getMessageId() { return id; }
  }
  static class ChatId { static boolean isMultiChat(long id) { return id<0; } }
  static class TdApi {
    static class MessageTopic {}
    static class Message { long id; boolean isOutgoing; Message(long i) { id=i; } }
    static class Chat {
      long id=-100123L,lastReadInboxMessageId=400,lastReadOutboxMessageId=0;
      int unreadCount=20; Message lastMessage=new Message(900);
    }
    static class MessageReplyInfo { int replyCount; long lastReadInboxMessageId,lastMessageId; }
    static class MessageThreadInfo {
      long chatId=-100123L; int unreadMessageCount=0;
      MessageReplyInfo replyInfo=new MessageReplyInfo();
      Message[] messages={new Message(700),new Message(600)};
    }
  }
  static class Td {
    static boolean hasUnread(TdApi.MessageReplyInfo i,long global) {
      return i!=null && i.lastMessageId>Math.max(i.lastReadInboxMessageId,global);
    }
  }
  static class ThreadInfo {
    static final int UNKNOWN_UNREAD_MESSAGE_COUNT=-1;
    TdApi.MessageThreadInfo threadInfo=new TdApi.MessageThreadInfo();
    TdApi.MessageTopic topic=new TdApi.MessageTopic();
    TdApi.MessageTopic getMessageTopicId() { return topic; }
    __METADATA__
  }
  static class Settings {
    static final Settings INSTANCE=new Settings();
    static Settings instance() { return INSTANCE; }
    SavedMessageId saved;
    SavedMessageId getScrollMessageId(int a,long c,TdApi.MessageTopic t) { return saved; }
    static class SavedMessageId {
      MessageId id; boolean readFully;
      SavedMessageId(long id,boolean fully) { this.id=new MessageId(-100123L,id); readFully=fully; }
    }
  }
  __ANCHORS__
  static class MessagesManager {
    static final int HIGHLIGHT_MODE_NONE=0,HIGHLIGHT_MODE_NORMAL=1,HIGHLIGHT_MODE_UNREAD=2,
      HIGHLIGHT_MODE_POSITION_RESTORE=3,HIGHLIGHT_MODE_UNREAD_NEXT=4;
    Controller controller() { return new Controller(); }
    int getUserScrollActionsCount() { return 0; }
  }
  static class Controller {
    boolean inPreviewMode() { return false; }
    boolean isInForceTouchMode() { return false; }
  }
  static class Loader {
    static final int SPECIAL_MODE_NONE=0, MODE_INITIAL=0, MODE_REPEAT_INITIAL=3,
      CHUNK_SIZE_SMALL=19, CHUNK_SEARCH_OFFSET=-19,CHUNK_SIZE_SEARCH=33;
    int specialMode=SPECIAL_MODE_NONE; Object searchFilter;
    MessagesManager manager=new MessagesManager();
    boolean canLoadTop,canLoadBottom,unreadNavigationPending,
      unreadPreviousCanLoadTop,unreadPreviousCanLoadBottom;
    int scrollHighlightMode,unreadNavigationScrollActions;
    long unreadNavigationBoundary; MessageId scrollMessageId;
    VisibleUnreadAnchor visibleUnreadAnchor;
    MessageId requestedId; int requestedOffset,requestedLimit;
    boolean requestedLocal;
    long getChatId() { return -100123L; }
    void reuse() { visibleUnreadAnchor=null; unreadNavigationPending=false; }
    void load(MessageId id,int offset,int limit,int mode,boolean local,boolean top,boolean bottom) {
      requestedId=id; requestedOffset=offset; requestedLimit=limit; requestedLocal=local;
    }
    __ENTRIES__
  }
  static int checks;
  static void check(boolean v,String why) { checks++; if(!v) throw new AssertionError(why); }
  static Loader open(DefaultAnchor a) {
    Loader loader=new Loader();
    if(a.messageId==null) loader.loadFromStart(new MessageId(loader.getChatId(),0));
    else loader.loadFromMessage(a.messageId,a.highlightMode,true);
    return loader;
  }
  public static void main(String[] args) {
    TdApi.Chat chat=new TdApi.Chat(); ThreadInfo thread=new ThreadInfo();
    check(thread.getReplyCount()==0 && !thread.hasUnreadMessages(chat),"zero-comment metadata is not unread");
    DefaultAnchor empty=resolveDefaultAnchor(0,chat,thread);
    check(empty.messageId==null && empty.highlightMode==HIGHLIGHT_MODE_NONE,
      "zero comments must open normal history, not missing unread target");
    Loader loader=open(empty);
    check(loader.requestedId.id==0 && loader.requestedOffset==0 && !loader.unreadNavigationPending,
      "normal empty entry uses supported history end and skips unread lookup");
    thread.threadInfo.replyInfo.replyCount=5;
    thread.threadInfo.replyInfo.lastMessageId=900;
    thread.threadInfo.replyInfo.lastReadInboxMessageId=900;
    check(resolveDefaultAnchor(0,chat,thread).messageId==null,
      "fully-read thread opens latest history without nonexistent unread search");
    Settings.instance().saved=new Settings.SavedMessageId(810,false);
    DefaultAnchor saved=resolveDefaultAnchor(0,chat,thread);
    check(saved.messageId.id==810 && saved.highlightMode==HIGHLIGHT_MODE_POSITION_RESTORE,
      "unfinished thread bookmark still restores exact position");
    Settings.instance().saved=new Settings.SavedMessageId(820,true);
    check(resolveDefaultAnchor(0,chat,thread).messageId.id==820,
      "fully-read saved thread still restores its bookmark");
    Settings.instance().saved=null;
    thread.threadInfo.unreadMessageCount=5;
    thread.threadInfo.replyInfo.lastReadInboxMessageId=0;
    DefaultAnchor initialUnread=resolveDefaultAnchor(0,chat,thread);
    check(initialUnread.highlightMode==HIGHLIGHT_MODE_UNREAD && initialUnread.messageId.id==700,
      "first unread lookup starts after the entire root album");
    loader=open(initialUnread);
    check(loader.unreadNavigationPending && loader.visibleUnreadAnchor.boundary()==700,
      "initial unread still uses production bounded lookup");
    check(loader.visibleUnreadAnchor.acceptPage(new long[]{900,800,700,600},
      new boolean[]{true,true,true,true},900)==VisibleUnreadAnchor.Result.FOUND &&
      loader.visibleUnreadAnchor.targetMessageId()==800,
      "root album members are excluded; earliest reply is selected");
    thread.threadInfo.replyInfo.lastReadInboxMessageId=800;
    DefaultAnchor unread=resolveDefaultAnchor(0,chat,thread);
    check(unread.messageId.id==800 && unread.highlightMode==HIGHLIGHT_MODE_UNREAD,
      "established thread read cursor remains unchanged");
    loader=new Loader();
    loader.loadFromMessage(new MessageId(chat.id,999),MessagesManager.HIGHLIGHT_MODE_NORMAL,true);
    check(loader.requestedId.id==999 && !loader.unreadNavigationPending,
      "explicit missing message keeps exact target and never enters default unread policy");
    System.out.println("Empty comment thread: "+checks+" production-method checks passed (TDLib/UI doubles)");
  }
}
'''.replace('__ANCHORS__', anchors).replace('__METADATA__', metadata).replace('__ENTRIES__', entries)
        with tempfile.TemporaryDirectory(prefix='empty-comment-test-') as directory:
            java = Path(directory) / 'EmptyCommentHarness.java'
            java.write_text(harness, encoding='utf-8')
            policy = BASE / 'component/chat/VisibleUnreadAnchor.java'
            subprocess.run(['javac', '-d', directory, str(policy), str(java)], check=True)
            subprocess.run(['java', '-cp', directory, 'EmptyCommentHarness'], check=True)

    def test_real_entry_and_error_boundaries(self):
        message = BASE / 'data/TGMessage.java'
        comment_button = block(message, 'public final void openMessageThread ()')
        self.assertIn('if (isChannel() || isChannelAutoForward())', comment_button)
        self.assertIn('highlightMessageId = null;', comment_button)
        opening = block(BASE / 'telegram/TdlibUi.java',
                        'public void openChat (final TdlibDelegate context, final @NonNull TdApi.Chat chatFinal,')
        self.assertIn('if (params != null && params.highlightSet)', opening)
        self.assertIn('MessagesManager.resolveDefaultAnchor(tdlib.id(), chat, messageThread)', opening)
        self.assertIn('UI.showToast(TD.isChannel(chatFinal.type) ? R.string.PostNotFound : R.string.MessageNotFound', opening)
        handler = block(LOADER, 'private Client.ResultHandler newHandler (')
        self.assertIn('UI.showError(object);', handler)
        self.assertNotIn('getReplyCount()', handler)


if __name__ == '__main__':
    unittest.main()
