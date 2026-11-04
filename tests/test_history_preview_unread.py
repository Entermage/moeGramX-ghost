import unittest
import test_history_preview as base


class UnreadPreviewTest(unittest.TestCase):
    run_java = base.HistoryPreviewTest.run_java

    def cache_sources(self):
        sources = base.HistoryPreviewTest.cache_sources(self)
        sources['Harness.java'] = '''
import org.thunderdog.challegram.component.chat.MessageHistoryPreview;
import org.thunderdog.challegram.telegram.Tdlib;
import org.drinkless.tdlib.TdApi;
import android.os.SystemClock;
public class Harness {
  static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
  static TdApi.Message m(long chat,long topic,long id){TdApi.Message m=new TdApi.Message();m.chatId=chat;m.id=id;m.topicId=new TdApi.MessageTopicForum(topic);return m;}
  static void put(Tdlib d,long topic,long id){MessageHistoryPreview.put(d,100,topic,new TdApi.Message[]{m(100,topic,id),m(100,topic,id-1)},id-1,7,false);}
  public static void main(String[] args){
    Tdlib d=new Tdlib();put(d,5,30);put(d,6,80);
    var first=MessageHistoryPreview.get(d,100,5,29,false);
    check(first!=null,"saved viewport");
    check(MessageHistoryPreview.get(d,100,5,100,false)==null,"strict anchor preserved");
    check(MessageHistoryPreview.get(d,100,5,0,true)==null,"strict tail preserved");
    check(MessageHistoryPreview.get(d,100,5,100,false,true)!=null,"unread outside cached window");
    check(MessageHistoryPreview.get(d,100,7,100,false,true)==null,"fallback cannot cross topics");
    check(MessageHistoryPreview.get(new Tdlib(),100,5,100,false,true)==null,"fallback cannot cross accounts");
    d.l.listener.onMessageEdited(100,80,1,null);
    check(MessageHistoryPreview.isValid(d,first),"other topic edit invalidated snapshot");
    check(MessageHistoryPreview.get(d,100,6,79,false)==null,"edited topic removed");
    d.l.listener.onMessagesDeleted(100,new long[]{200,201});
    check(MessageHistoryPreview.isValid(d,first),"uncached deletion invalidated snapshot");
    put(d,6,90);check(MessageHistoryPreview.isValid(d,first),"new window invalidated unrelated in-flight parse");
    d.l.listener.onMessageContentChanged(100,29,new TdApi.MessageContent());
    check(!MessageHistoryPreview.isValid(d,first),"changed cached content must invalidate parse");
    put(d,5,30);var old=MessageHistoryPreview.get(d,100,5,29,false);
    put(d,5,40);check(!MessageHistoryPreview.isValid(d,old),"replacement invalidates old parse");
    SystemClock.now=299999;var nearExpiry=MessageHistoryPreview.get(d,100,5,39,false);
    SystemClock.now=300001;check(!MessageHistoryPreview.isValid(d,nearExpiry),"copy must not extend TTL");
    check(MessageHistoryPreview.get(d,100,5,99,false,true)==null,"expired unread fallback");
    System.out.println("15 preview lifetime assertions passed");
  }
}'''
        return sources

    def test_unread_fallback_and_targeted_invalidation(self):
        r = self.run_java(self.cache_sources())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_whole_chat_invalidation_negative_control(self):
        sources = self.cache_sources()
        key = 'org/thunderdog/challegram/component/chat/MessageHistoryPreview.java'
        sources[key] = sources[key].replace(
            'for (long id : messageIds) if (message.id == id) return true;',
            'for (long id : messageIds) return true;')
        r = self.run_java(sources)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('other topic edit', r.stderr)

    def entry_sources(self):
        method = base.method((base.SRC/'component/chat/MessagesLoader.java').read_text(),
                             '  private void tryHistoryPreview (')
        code = '''import java.util.*;
public class Harness {
  static class MessagesManager {static final int HIGHLIGHT_MODE_NONE=0,HIGHLIGHT_MODE_UNREAD=2,HIGHLIGHT_MODE_POSITION_RESTORE=3,HIGHLIGHT_MODE_UNREAD_NEXT=4;}
  static class MessageId {long getMessageId(){return 90;}boolean isHistoryEnd(){return false;}}
  static class MessageHistoryPreview {
    static class Window {Object messages;}
    static boolean fallback,valid=true,none;static int gets;
    static Window get(Object d,long c,long t,long id,boolean latest,boolean allow){gets++;fallback=allow;return none?null:new Window();}
    static boolean isValid(Object d,Window w){return valid;}
  }
  static class Background {static final Background b=new Background();List<Runnable> tasks=new ArrayList<>();static Background instance(){return b;}void post(Runnable r){tasks.add(r);}void flush(){var copy=new ArrayList<>(tasks);tasks.clear();copy.forEach(Runnable::run);}}
  static class Adapter {int rows;int getMessageCount(){return rows;}}
  static class Manager {Adapter adapter=new Adapter();Adapter getAdapter(){return adapter;}}
  static final int MODE_INITIAL=0;
  boolean historyPreviewAttempted,historyPublished,supported=true;int scrollHighlightMode;
  long contextId=1;Object tdlib;Manager manager=new Manager();int parsed,local;boolean localUnread;
  boolean supportsHistoryPreview(){return supported;}long getChatId(){return 100;}long historyPreviewTopic(){return 5;}
  void processMessages(long c,Object messages,int count,Object next,int offset,boolean find,Object missing,MessageHistoryPreview.Window w){parsed++;}
  void tryLocalTopicPreview(MessageId from,boolean unread){local++;localUnread=unread;}
''' + method + '''
  static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
  public static void main(String[] args){
    for(int mode:new int[]{0,2,3,4}){Harness h=new Harness();h.scrollHighlightMode=mode;
      h.tryHistoryPreview(new MessageId(),0);Background.b.flush();check(h.parsed==1,"entry skipped preview mode="+mode);
      check(MessageHistoryPreview.fallback==(mode==2||mode==4),"only unread accepts previous position");
      h.tryHistoryPreview(new MessageId(),0);Background.b.flush();check(h.parsed==1,"duplicate parse");}
    for(int mode:new int[]{1,5}){Harness h=new Harness();h.scrollHighlightMode=mode;h.tryHistoryPreview(new MessageId(),0);Background.b.flush();check(h.parsed==0,"explicit message link must retain navigation");}
    Harness h=new Harness();h.scrollHighlightMode=2;h.tryHistoryPreview(new MessageId(),0);h.contextId++;Background.b.flush();check(h.parsed==0,"stale generation");
    h=new Harness();h.tryHistoryPreview(new MessageId(),0);h.historyPublished=true;Background.b.flush();check(h.parsed==0,"fresh page already published");
    h=new Harness();h.tryHistoryPreview(new MessageId(),0);MessageHistoryPreview.valid=false;Background.b.flush();check(h.parsed==0,"edited snapshot during parse");MessageHistoryPreview.valid=true;
    h=new Harness();h.manager.adapter.rows=3;h.tryHistoryPreview(new MessageId(),0);Background.b.flush();check(h.parsed==0,"existing rows cannot be replaced");
    h=new Harness();h.supported=false;h.tryHistoryPreview(new MessageId(),0);Background.b.flush();check(h.parsed==0,"secret and special scopes excluded");
    h=new Harness();h.tryHistoryPreview(new MessageId(),1);Background.b.flush();check(h.parsed==0,"pagination is not initial entry");
    check(h.local==0,"remembered window never falls back to local history");
    // Without a remembered window the same entries look for the topic's stored messages instead.
    MessageHistoryPreview.none=true;
    for(int mode:new int[]{0,2,3,4}){h=new Harness();h.scrollHighlightMode=mode;h.tryHistoryPreview(new MessageId(),0);Background.b.flush();
      check(h.local==1&&h.parsed==0&&h.localUnread==(mode==2||mode==4),"missing window must try local topic history mode="+mode);
      h.tryHistoryPreview(new MessageId(),0);check(h.local==1,"local fallback attempted twice");}
    for(int mode:new int[]{1,5}){h=new Harness();h.scrollHighlightMode=mode;h.tryHistoryPreview(new MessageId(),0);check(h.local==0,"message link must not show local fallback");}
    h=new Harness();h.manager.adapter.rows=3;h.tryHistoryPreview(new MessageId(),0);check(h.local==0,"local fallback over existing rows");
    h=new Harness();h.tryHistoryPreview(new MessageId(),1);check(h.local==0,"local fallback on pagination");
    MessageHistoryPreview.none=false;
    System.out.println("33 entry assertions passed");
  }
}'''
        return {'Harness.java': code}

    def test_unread_entry_and_callback_guards(self):
        r = self.run_java(self.entry_sources())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unread_skip_negative_control(self):
        sources = self.entry_sources()
        sources['Harness.java'] = sources['Harness.java'].replace(
            'if (!unreadEntry && scrollHighlightMode', 'if (scrollHighlightMode')
        r = self.run_java(sources)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('entry skipped preview mode=2', r.stderr)

    def test_complete_preview_releases_native_readiness(self):
        production = base.method((base.SRC/'component/chat/MessagesManager.java').read_text(),
                                 '  public void displayHistoryPreview (')
        code = '''import java.util.*;public class Harness {
  static class MessageHistoryPreview {static final int OFFSET_TOP=Integer.MIN_VALUE;}
  static class TGMessage {long id;int builtWidth;TGMessage(long id){this.id=id;}void buildLayout(int w){builtWidth=w;}int getHeight(){return 40+(int)id;}}
  static class Adapter {
    ArrayList<TGMessage> rows;void resetMessages(ArrayList<TGMessage> value){rows=value;}
    TGMessage getMessage(int i){return rows.get(i);}
    int indexOfMessageContainer(long id){for(int i=0;i<rows.size();i++)if(rows.get(i).id==id)return i;return -1;}
  }
  Adapter adapter=new Adapter();int position,offset,ready;
  int getRecyclerWidth(){return 300;}int getTargetHeight(){return 900;}
  void scrollToPositionWithOffsetImpl(int p,int o){position=p;offset=o;}
  void onChatAwaitFinish(){if(adapter.rows.isEmpty())throw new AssertionError("empty preview released navigation");ready++;}
''' + production + '''
  public static void main(String[] args){Harness h=new Harness();ArrayList<TGMessage> page=new ArrayList<>();
    h.displayHistoryPreview(page,0,0);if(h.ready!=0)throw new AssertionError("empty preview");
    for(int i=30;i>0;i--)page.add(new TGMessage(i));
    h.displayHistoryPreview(page,20,14);
    if(h.ready!=1||h.adapter.rows.size()!=30||h.position!=10||h.offset!=14)throw new AssertionError("full viewport must be placed before readiness");
    h.displayHistoryPreview(page,20,MessageHistoryPreview.OFFSET_TOP);
    if(h.position!=10||h.offset!=900-60||page.get(10).builtWidth!=300)throw new AssertionError("unread anchor must sit at the top like an unread entry");
    h.displayHistoryPreview(page,99,MessageHistoryPreview.OFFSET_TOP);
    if(h.position!=0||h.offset!=0)throw new AssertionError("missing anchor falls back to the bottom");
  }}'''
        r = self.run_java({'Harness.java': code})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fresh_unread_page_replaces_snapshot_and_keeps_target(self):
        production = base.method((base.SRC/'component/chat/MessagesManager.java').read_text(),
                                 '  public void replaceUnreadHistoryPreview (')
        code = '''import java.util.*;public class Harness {
  static class TGMessage {boolean destroyed;void onDestroy(){destroyed=true;}}static class MessageId{}
  static class MessagesLoader {static final int MODE_REPEAT_INITIAL=1;}
  static class Adapter {ArrayList<TGMessage> rows=new ArrayList<>();int getMessageCount(){return rows.size();}TGMessage getMessage(int i){return rows.get(i);}}
  Adapter adapter=new Adapter();int receivedMode,receivedPosition,receivedHighlight;TGMessage receivedMessage;MessageId receivedId;
  void displayMessages(ArrayList<TGMessage> rows,int mode,int position,TGMessage message,MessageId id,int highlight,boolean repeat,boolean top){adapter.rows=new ArrayList<>(rows);receivedMode=mode;receivedPosition=position;receivedHighlight=highlight;receivedMessage=message;receivedId=id;}
''' + production + '''
  public static void main(String[] args){Harness h=new Harness();TGMessage stale=new TGMessage(),fresh=new TGMessage();MessageId id=new MessageId();h.adapter.rows.add(stale);
    h.replaceUnreadHistoryPreview(new ArrayList<>(List.of(fresh)),7,fresh,id,2,false,true);
    if(h.adapter.rows.size()!=1||h.adapter.rows.get(0)!=fresh||!stale.destroyed||fresh.destroyed)throw new AssertionError("duplicate or leaked preview rows");
    if(h.receivedMode!=1||h.receivedPosition!=7||h.receivedHighlight!=2||h.receivedMessage!=fresh||h.receivedId!=id)throw new AssertionError("unread target swallowed by preview");
  }}'''
        r = self.run_java({'Harness.java': code})
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
