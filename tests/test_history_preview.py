import pathlib, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/org/thunderdog/challegram'

def method(text, signature):
    start=text.index(signature); brace=text.index('{',start); depth=1; end=brace+1
    while depth:
        depth += (text[end]=='{')-(text[end]=='}'); end+=1
    return text[start:end]

class HistoryPreviewTest(unittest.TestCase):
    def run_java(self, sources):
        with tempfile.TemporaryDirectory() as folder:
            d=pathlib.Path(folder)
            for name,content in sources.items():
                p=d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
            r=subprocess.run(['javac','-d',str(d),*[str(p) for p in d.rglob('*.java')]],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            return subprocess.run(['java','-cp',str(d),'Harness'],capture_output=True,text=True)

    def cache_sources(self):
        return {
          'org/thunderdog/challegram/component/chat/MessageHistoryPreview.java':(SRC/'component/chat/MessageHistoryPreview.java').read_text(),
          'android/os/SystemClock.java':'package android.os; public class SystemClock {public static long now; public static long uptimeMillis(){return now;}}',
          'org/drinkless/tdlib/TdApi.java':'''package org.drinkless.tdlib; public class TdApi {
            public static class Message {public long id,chatId; public Object topicId,sendingState,schedulingState,selfDestructType; public double autoDeleteIn;}
            public static class MessageTopicForum {public long forumTopicId; public MessageTopicForum(long id){forumTopicId=id;}}
            public static class MessageContent{} public static class EphemeralMessageContent{} public static class ReplyMarkup{} public static class Error{}}''',
          'org/thunderdog/challegram/telegram/MessageListener.java':'''package org.thunderdog.challegram.telegram; import org.drinkless.tdlib.TdApi;
            public interface MessageListener {
            default void onMessageContentChanged(long c,long id,TdApi.MessageContent content){}
            default void onMessageEphemeralContentChanged(long c,long id,TdApi.EphemeralMessageContent content){}
            default void onMessageEdited(long c,long id,int d,TdApi.ReplyMarkup r){}
            default void onMessagesDeleted(long c,long[] ids){}
            default void onMessageSendSucceeded(TdApi.Message m,long old){}
            default void onMessageSendFailed(TdApi.Message m,long old,TdApi.Error e){} }''',
          'org/thunderdog/challegram/telegram/Tdlib.java':'''package org.thunderdog.challegram.telegram;
            public class Tdlib {public boolean isAuthorized(){return true;}public final Listeners l=new Listeners(); public Listeners listeners(){return l;}
            public static class Listeners {public MessageListener listener; public void subscribeForGlobalUpdates(Object o){listener=(MessageListener)o;} public void unsubscribeFromGlobalUpdates(Object o){if(listener==o)listener=null;}}}''',
          'tgx/td/Td.java':'''package tgx.td; import org.drinkless.tdlib.TdApi; public class Td {
            public static TdApi.Message copyOf(TdApi.Message m){TdApi.Message c=new TdApi.Message();c.id=m.id;c.chatId=m.chatId;c.topicId=m.topicId;return c;}}''',
          'Harness.java':'''import org.thunderdog.challegram.component.chat.MessageHistoryPreview;
            import org.thunderdog.challegram.telegram.Tdlib; import org.drinkless.tdlib.TdApi; import android.os.SystemClock;
            public class Harness {
            static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
            static TdApi.Message m(long c,long t,long id){TdApi.Message m=new TdApi.Message();m.chatId=c;m.id=id;if(t!=0)m.topicId=new TdApi.MessageTopicForum(t);return m;}
            static void put(Tdlib d,long c,long t){MessageHistoryPreview.put(d,c,t,new TdApi.Message[]{m(c,t,30),m(c,t,20)},20,7,true);}
            public static void main(String[] a){
              Tdlib x=new Tdlib(),y=new Tdlib();put(x,100,5);
              var w=MessageHistoryPreview.get(x,100,5,20,false);check(w!=null&&w.offset==7,"anchor");
              check(MessageHistoryPreview.get(y,100,5,20,false)==null,"account isolation");
              check(MessageHistoryPreview.get(x,100,6,20,false)==null,"topic isolation");
              check(MessageHistoryPreview.get(x,100,5,10,false)==null,"window boundary");
              w.messages[0].id=999;check(MessageHistoryPreview.get(x,100,5,20,false).messages[0].id==30,"envelope copy");
              x.l.listener.onMessagesDeleted(100,new long[]{20});check(!MessageHistoryPreview.isValid(x,w),"stale queued preview");
              check(MessageHistoryPreview.get(x,100,5,20,false)==null,"deletion invalidates");
              put(x,100,5);x.l.listener.onMessageContentChanged(100,20,new TdApi.MessageContent());check(MessageHistoryPreview.get(x,100,5,20,false)==null,"edit invalidates");
              for(int i=1;i<=7;i++)put(x,i,5);check(MessageHistoryPreview.get(x,1,5,20,false)==null,"bounded windows");
              check(MessageHistoryPreview.get(x,7,5,0,true)!=null,"latest retained");
              SystemClock.now=300001;check(MessageHistoryPreview.get(x,7,5,20,false)==null,"expiry");
              put(x,8,5);MessageHistoryPreview.clear(x);check(x.l.listener==null,"detach listener");
              check(MessageHistoryPreview.get(x,8,5,20,false)==null,"account teardown");
              TdApi.Message[] tooMany=new TdApi.Message[81];for(int i=0;i<81;i++)tooMany[i]=m(9,5,100-i);
              MessageHistoryPreview.put(x,9,5,tooMany,30,0,true);check(MessageHistoryPreview.get(x,9,5,30,false)==null,"message bound");
              TdApi.Message pending=m(10,5,1);pending.sendingState=new Object();MessageHistoryPreview.put(x,10,5,new TdApi.Message[]{pending},1,0,true);check(MessageHistoryPreview.get(x,10,5,1,false)==null,"no pending");
              MessageHistoryPreview.put(x,11,5,new TdApi.Message[]{m(11,6,1)},1,0,true);check(MessageHistoryPreview.get(x,11,5,1,false)==null,"reject wrong topic");
              System.out.println("cache lifecycle checks passed");}}'''
        }

    def test_cache_lifecycle(self):
        r=self.run_java(self.cache_sources());self.assertEqual(r.returncode,0,r.stderr)

    def test_unbounded_cache_negative_control(self):
        s=self.cache_sources();key='org/thunderdog/challegram/component/chat/MessageHistoryPreview.java'
        s[key]=s[key].replace('MAX_WINDOWS = 6','MAX_WINDOWS = 100')
        r=self.run_java(s);self.assertNotEqual(r.returncode,0);self.assertIn('bounded windows',r.stderr)

    def merge_sources(self):
        production=method((SRC/'component/chat/MessagesManager.java').read_text(),'  public void replaceHistoryPreview (')
        return {'Harness.java':'''import java.util.*;
          public class Harness {
          static class TdApi {static class Message {long id;Message(long id){this.id=id;}}}
          static class View {Object getParent(){return this;}}
          static class TGMessage {long[] ids;boolean destroyed,hidden;String text="old";TGMessage(long...ids){this.ids=ids;}
            long getBiggestId(){return ids[0];}long getSmallestId(){return ids[ids.length-1];}
            boolean isSponsoredMessage(){return false;}boolean isThreadHeader(){return false;}
            TdApi.Message[] getAllMessages(){return Arrays.stream(ids).mapToObj(TdApi.Message::new).toArray(TdApi.Message[]::new);}
            void mergeWith(TGMessage p,boolean b){}void prepareLayout(){}void onDestroy(){destroyed=true;}}
          static class Adapter {ArrayList<TGMessage> rows=new ArrayList<>();int getMessageCount(){return rows.size();}
            TGMessage getMessage(int p){return p<0||p>=rows.size()?null:rows.get(p);}
            int indexOfMessageContainer(long id){for(int i=0;i<rows.size();i++)for(long v:rows.get(i).ids)if(v==id)return i;return -1;}
            void resetMessages(ArrayList<TGMessage> r){rows=new ArrayList<>(r);}}
          static class Layout {int first;int findFirstVisibleItemPosition(){return first;}View findViewByPosition(int p){return new View();}}
          static class MoexMessageFilter {static boolean shouldHideInChat(Object tdlib,TdApi.Message m,boolean c){return hidden.contains(m.id);}}
          static Set<Long> hidden=new HashSet<>();Object tdlib;Adapter adapter=new Adapter();Layout manager=new Layout();boolean bottom;int scrolled,offset;
          int calculateOffsetInPixels(View v,int p){return 17;}boolean isAtVeryBottom(){return bottom;}boolean isChannel(){return false;}
          void scrollToPositionWithOffsetImpl(int p,int o){scrolled=p;offset=o;}void checkTopEndReached(ArrayList<TGMessage> r,boolean w,boolean c){}void onChatAwaitFinish(){}void viewMessages(boolean b){}
        '''+production+'''
          static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
          static ArrayList<TGMessage> rows(long...ids){ArrayList<TGMessage> r=new ArrayList<>();for(long id:ids)r.add(new TGMessage(id));return r;}
          static TdApi.Message[] raw(long...ids){return Arrays.stream(ids).mapToObj(TdApi.Message::new).toArray(TdApi.Message[]::new);}
          public static void main(String[] args){
            Harness h=new Harness();h.adapter.rows=rows(3,2,1);h.manager.first=2;
            h.replaceHistoryPreview(rows(4,3,2),raw(4,3,2),false,true,false);
            check(h.adapter.rows.size()==4&&h.scrolled==3&&h.offset==17,"anchor survives append");
            h=new Harness();h.bottom=true;h.adapter.rows=rows(3,2,1);h.replaceHistoryPreview(rows(4,3,2),raw(4,3,2),false,true,false);check(h.scrolled==0&&h.offset==0,"follow bottom");
            h=new Harness();h.adapter.rows=rows(3,2,1);TGMessage removed=h.adapter.rows.get(1);h.replaceHistoryPreview(rows(4,3,1),raw(4,3,1),false,true,false);check(h.adapter.indexOfMessageContainer(2)==-1&&removed.destroyed,"authoritative deletion");
            h=new Harness();h.adapter.rows=rows(3,2,1);h.replaceHistoryPreview(rows(9,8),raw(9,8),false,true,false);check(h.adapter.rows.size()==2,"disjoint windows");
            h=new Harness();h.adapter.rows=rows(3,2,1);hidden.add(1L);h.replaceHistoryPreview(rows(4,3,2),raw(4,3,2),false,true,false);check(h.adapter.rows.size()==3,"refilter retained");hidden.clear();
            h=new Harness();h.adapter.rows.add(new TGMessage(3,2));h.replaceHistoryPreview(new ArrayList<>(List.of(new TGMessage(4,3,2))),raw(4,3,2),false,true,false);check(h.adapter.rows.size()==1,"album dedup");
            h=new Harness();h.adapter.rows=rows(5,3,2);h.replaceHistoryPreview(rows(4,3,2),raw(4,3,2),false,true,false);check(h.adapter.rows.get(0).getBiggestId()==5,"live message survives");
            h=new Harness();h.adapter.rows=rows(3,2,1);h.manager.first=2;h.replaceHistoryPreview(rows(9,8,7),raw(9,8,7),false,true,true);check(h.scrolled==0&&h.offset==0&&h.adapter.rows.size()==3,"arrow end page at the bottom");
            h=new Harness();h.adapter.rows=rows(5,4,3);h.manager.first=2;h.replaceHistoryPreview(rows(6,5,4),raw(6,5,4),false,true,true);check(h.scrolled==0&&h.adapter.rows.size()==4,"arrow end page joins an overlapping snapshot at the bottom");
            System.out.println("merge and viewport checks passed");}}'''}

    def test_merge_and_viewport(self):
        r=self.run_java(self.merge_sources());self.assertEqual(r.returncode,0,r.stderr)

    def test_arrow_end_viewport_negative_control(self):
        s=self.merge_sources();s['Harness.java']=s['Harness.java'].replace('if (followBottom || toEnd) scrollToPositionWithOffsetImpl(0, 0);','if (followBottom) scrollToPositionWithOffsetImpl(0, 0);')
        r=self.run_java(s);self.assertNotEqual(r.returncode,0);self.assertIn('arrow end page at the bottom',r.stderr)

    def test_disjoint_merge_negative_control(self):
        s=self.merge_sources();s['Harness.java']=s['Harness.java'].replace('if (overlap) {','if (true) {')
        r=self.run_java(s);self.assertNotEqual(r.returncode,0);self.assertIn('disjoint windows',r.stderr)

if __name__=='__main__': unittest.main()
