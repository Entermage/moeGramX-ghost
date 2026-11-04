"""Production request reconciliation, draft equality and atomic read-progress regressions."""
from pathlib import Path
import unittest
from test_forum_requests import STUBS, SOURCE
from test_forum_navigation_counters import run_java
from test_forum_scope import method

P = SOURCE.parents[4]
TOPICS = SOURCE.parent

SYNC = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
public class SyncHarness {
 static int checks;
 static void check(boolean b,String msg){checks++;if(!b)throw new AssertionError(msg);}
 static TdApi.ForumTopic topic(long chat,int id){
  return new TdApi.ForumTopic(new TdApi.ForumTopicInfo(chat,id,"old"),new TdApi.Message(100),12,false,8,20,80,1,2,3,new TdApi.ChatNotificationSettings(0),new TdApi.DraftMessage(100,"old"));
 }
 static TdApi.UpdateForumTopic update(long chat,int id){
  TdApi.UpdateForumTopic u=new TdApi.UpdateForumTopic();u.chatId=chat;u.forumTopicId=id;u.isPinned=true;u.lastReadInboxMessageId=100;u.lastReadOutboxMessageId=40;
  u.unreadMentionCount=4;u.unreadReactionCount=5;u.unreadPollVoteCount=6;u.notificationSettings=new TdApi.ChatNotificationSettings(900);u.draftMessage=new TdApi.DraftMessage(100,"new");return u;
 }
 static void finish(Tdlib t,int index,TdApi.Object value){t.calls.get(index).handler.onResult(value,null);t.clock.advance(0);}
 static void request(Tdlib t,int id){ForumRequests.send(t,new Object(),new TdApi.GetForumTopic(-100,id),(r,e)->{});}
 public static void main(String[] args){
  Tdlib t=new Tdlib();TdApi.ForumTopic original=topic(-100,7);TdApi.ForumTopic[] got=new TdApi.ForumTopic[2];
  ForumRequests.send(t,new Object(),new TdApi.GetForumTopic(-100,7),(r,e)->got[0]=r);
  ForumRequests.onTopicInfo(t,new TdApi.ForumTopicInfo(-100,7,"new"));ForumRequests.onTopicUpdate(t,update(-100,7));
  ForumRequests.send(t,new Object(),new TdApi.GetForumTopic(-100,7),(r,e)->got[1]=r);
  check(t.calls.size()==1,"joining observer shares native request");finish(t,0,original);
  check(got[0].info.name.equals("new"),"new info survives stale snapshot");
  check(got[1]==got[0],"late observer receives same reconciled snapshot");
  check(got[0].isPinned && got[0].notificationSettings.muteFor==900,"pin and mute survive");
  check(got[0].unreadMentionCount==4 && got[0].unreadReactionCount==5 && got[0].unreadPollVoteCount==6,"counters survive");
  check(got[0].draftMessage.text.equals("new"),"same-second updated draft survives");
  check(got[0].lastReadInboxMessageId==100 && got[0].lastReadOutboxMessageId==80 && got[0].unreadCount==0,"read progress never regresses");
  check(original.info.name.equals("old") && original.unreadCount==8 && !original.isPinned,"shared response is not mutated");
  Tdlib page=new Tdlib();TdApi.ForumTopics[] out=new TdApi.ForumTopics[1];
  ForumRequests.send(page,new Object(),new TdApi.GetForumTopics(-200,"",0,0,0,50),(r,e)->out[0]=r);
  TdApi.ForumTopic a=topic(-200,7),b=topic(-200,8);TdApi.ForumTopics raw=new TdApi.ForumTopics(20,new TdApi.ForumTopic[]{a,b},10,1000,8);
  ForumRequests.onTopicInfo(page,new TdApi.ForumTopicInfo(-200,7,"first"));ForumRequests.onTopicInfo(page,new TdApi.ForumTopicInfo(-200,7,"latest"));
  ForumRequests.onTopicInfo(page,new TdApi.ForumTopicInfo(-201,8,"wrong chat"));ForumRequests.onTopicInfo(t,new TdApi.ForumTopicInfo(-200,8,"wrong account"));finish(page,0,raw);
  check(out[0].topics[0].info.name.equals("latest") && out[0].topics[1]==b,"page uses latest matching update only");
  check(out[0].totalCount==20 && out[0].nextOffsetMessageId==1000 && raw.topics[0]==a,"page cursor and original preserved");
  Tdlib q=new Tdlib();request(q,1);request(q,2);TdApi.ForumTopic[] queued=new TdApi.ForumTopic[1];
  ForumRequests.send(q,new Object(),new TdApi.GetForumTopic(-100,3),(r,e)->queued[0]=r);
  ForumRequests.onTopicInfo(q,new TdApi.ForumTopicInfo(-100,3,"before native dispatch"));finish(q,0,topic(-100,1));
  check(q.calls.size()==3,"queued request starts after slot release");finish(q,2,topic(-100,3));
  check(queued[0].info.name.equals("old"),"queued request does not replay pre-dispatch update");
  Tdlib expired=new Tdlib();int[] callbacks={0};
  ForumRequests.send(expired,new Object(),new TdApi.GetForumTopic(-100,7),(r,e)->{callbacks[0]++;check(e!=null && e.code==504,"timeout response");});
  ForumRequests.onTopicUpdate(expired,update(-100,7));expired.clock.advance(30001);
  check(ForumRequests.snapshot(expired)[0]==1,"timeout retains native slot");
  ForumRequests.onTopicInfo(expired,new TdApi.ForumTopicInfo(-100,7,"after timeout"));finish(expired,0,topic(-100,7));
  check(callbacks[0]==1 && ForumRequests.snapshot(expired)[0]==0,"late callback only releases gate");
  Tdlib overflow=new Tdlib();int[] code={0};
  ForumRequests.send(overflow,new Object(),new TdApi.GetForumTopics(-300,"",0,0,0,50),(r,e)->{code[0]=e==null?0:e.code;check(r==null,"overflow cannot publish stale page");});
  for(int i=0;i<257;i++)ForumRequests.onTopicInfo(overflow,new TdApi.ForumTopicInfo(-300,i,"new"));
  check(ForumRequests.snapshot(overflow)[0]==1,"journal cap never releases native slot early");finish(overflow,0,raw);
  check(code[0]==503 && ForumRequests.snapshot(overflow)[0]==0,"bounded journal overflow fails explicitly");
  Tdlib closed=new Tdlib();int[] old={0};TdApi.Error[] oldError={null};ForumRequests.send(closed,new Object(),new TdApi.GetForumTopic(-100,7),(r,e)->{old[0]++;oldError[0]=e;});
  ForumRequests.onTopicInfo(closed,new TdApi.ForumTopicInfo(-100,7,"closed"));ForumRequests.onClientClosed(closed);
  // Closing ends each waiter once with a distinguishable error (the caller resets its loading state).
  check(old[0]==1 && ForumRequests.isClientClosed(oldError[0]),"closing ends the old waiter once");
  TdApi.ForumTopic[] fresh=new TdApi.ForumTopic[1];ForumRequests.send(closed,new Object(),new TdApi.GetForumTopic(-100,7),(r,e)->fresh[0]=r);
  finish(closed,0,topic(-100,7));check(old[0]==1 && fresh[0]==null && ForumRequests.snapshot(closed)[0]==1,"old client cannot complete new request");
  finish(closed,1,topic(-100,7));check(fresh[0].info.name.equals("old"),"closed journal not reused");
  System.out.println("PASS "+checks+" reconciliation assertions");
 }
}'''

DRAFT = r'''
import org.drinkless.tdlib.TdApi;import tgx.td.Td;import androidx.annotation.Nullable;
public class DraftHarness {
 LIST
 SCREEN
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args){
  TdApi.DraftMessage a=new TdApi.DraftMessage(100,"hello"),b=new TdApi.DraftMessage(100,"changed");
  check(!sameDraft(a,b),"list detects same-second edit");check(!xgramSameDraft(a,b),"composer detects same-second edit");
  check(sameDraft(a,new TdApi.DraftMessage(100,"hello")),"identical list draft");check(xgramSameDraft(a,new TdApi.DraftMessage(100,"hello")),"identical composer draft");
  check(sameDraft(null,null)&&!sameDraft(a,null),"list null semantics");check(xgramSameDraft(null,new TdApi.DraftMessage(0,"")),"composer empty semantics");
 }
}'''

OUTBOX = r'''
package moe.kirao.mgx.topics;
import java.util.concurrent.*;import org.thunderdog.challegram.telegram.Tdlib;
public class OutboxHarness {
 public static final CountDownLatch captured=new CountDownLatch(1),release=new CountDownLatch(1);
 public static class RaceMap<K,V> extends ConcurrentHashMap<K,V>{
  @Override public V get(Object key){V value=super.get(key);if(Thread.currentThread().getName().equals("low")){captured.countDown();try{if(!release.await(3,TimeUnit.SECONDS))throw new AssertionError("race timeout");}catch(InterruptedException e){throw new AssertionError(e);}}return value;}
 }
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args)throws Exception{
  Tdlib t=new Tdlib();XgramTopicReadOutbox.set(t,-100,7,20);
  Thread low=new Thread(()->{try{XgramTopicReadOutbox.set(t,-100,7,100);}finally{captured.countDown();}},"low");low.start();
  check(captured.await(3,TimeUnit.SECONDS),"writer reaches deterministic checkpoint");XgramTopicReadOutbox.set(t,-100,7,200);release.countDown();low.join(3000);
  check(!low.isAlive(),"writer completes");check(XgramTopicReadOutbox.get(t,-100,7)==200,"concurrent read progress never regresses");
  check(!XgramTopicReadOutbox.set(t,-100,7,100),"older snapshot is ignored");
  check(XgramTopicReadOutbox.set(t,-100,8,300),"separate topic advances");
  XgramTopicReadOutbox.forgetAccount(t.id());check(XgramTopicReadOutbox.get(t,-100,7)==0,"account cleanup");
 }
}'''

def files():
    result = dict(STUBS)
    result.pop('moe/kirao/mgx/topics/QueueHarness.java')
    return result

class ForumSyncRaceTests(unittest.TestCase):
    def sync(self, negative=False):
        f=files()
        source=SOURCE.read_text()
        if negative: source=source.replace('result = entry.updates.apply(result);','// negative control: unprotected snapshot')
        f['moe/kirao/mgx/topics/ForumRequests.java']=source
        f['moe/kirao/mgx/topics/ForumTopicSnapshotUpdates.java']=(TOPICS/'ForumTopicSnapshotUpdates.java').read_text()
        f['moe/kirao/mgx/topics/SyncHarness.java']=SYNC
        return run_java(f,'moe.kirao.mgx.topics.SyncHarness')

    def test_updates_survive_inflight_requests_and_lifecycle(self):
        r=self.sync();self.assertEqual(r.returncode,0,r.stderr)

    def test_negative_snapshot_replacement(self):
        r=self.sync(True);self.assertNotEqual(r.returncode,0);self.assertIn('new info survives stale snapshot',r.stderr)

    def draft(self,negative=False):
        f=files()
        list_method=method((TOPICS/'ForumTopicList.java').read_text(),'private static boolean sameDraft (')
        screen_method=method((P/'org/thunderdog/challegram/ui/MessagesController.java').read_text(),'private static boolean xgramSameDraft (')
        if negative: list_method=list_method.replace('tgx.td.Td.equalsTo(a, b)','a.date == b.date')
        f['androidx/annotation/Nullable.java']='package androidx.annotation;public @interface Nullable {}'
        # The existing TDLib equality implementation is not under test; these assert the call-site policy.
        f['tgx/td/Td.java']='package tgx.td;import org.drinkless.tdlib.TdApi;public class Td {public static boolean equalsTo(TdApi.DraftMessage a,TdApi.DraftMessage b){return a.date==b.date&&a.text.equals(b.text);}public static boolean isEmpty(TdApi.DraftMessage a){return a==null||a.text.isEmpty();}}'
        f['DraftHarness.java']=DRAFT.replace('LIST',list_method).replace('SCREEN',screen_method)
        return run_java(f,'DraftHarness')

    def test_draft_change_with_equal_timestamp(self):
        r=self.draft();self.assertEqual(r.returncode,0,r.stderr)

    def test_negative_date_only_draft(self):
        r=self.draft(True);self.assertNotEqual(r.returncode,0);self.assertIn('same-second edit',r.stderr)

    def outbox(self,negative=False):
        f=files();source=(TOPICS/'XgramTopicReadOutbox.java').read_text()
        if negative:
            start=source.index('    boolean[] advanced')
            end=source.index('    return advanced[0];',start)+len('    return advanced[0];')
            source=source[:start]+'''    Long old = readOutbox.get(key);
    if (old != null && old >= lastReadOutboxMessageId) return false;
    readOutbox.put(key, lastReadOutboxMessageId);return true;'''+source[end:]
        source=source.replace('new ConcurrentHashMap<>()','new OutboxHarness.RaceMap<>()')
        f['moe/kirao/mgx/topics/XgramTopicReadOutbox.java']=source
        f['moe/kirao/mgx/topics/XgramForums.java']='package moe.kirao.mgx.topics;public class XgramForums {static final int GENERAL_TOPIC_ID=1;}'
        f['org/thunderdog/challegram/telegram/Tdlib.java']=f['org/thunderdog/challegram/telegram/Tdlib.java'].replace('public class Tdlib {','public class Tdlib {public int id(){return 1;}public boolean isForum(long id){return true;}')
        f['androidx/annotation/Nullable.java']='package androidx.annotation;public @interface Nullable {}'
        f['moe/kirao/mgx/topics/OutboxHarness.java']=OUTBOX
        return run_java(f,'moe.kirao.mgx.topics.OutboxHarness')

    def test_atomic_outbox_progress(self):
        r=self.outbox();self.assertEqual(r.returncode,0,r.stderr)

    def test_negative_nonatomic_outbox_progress(self):
        r=self.outbox(True);self.assertNotEqual(r.returncode,0);self.assertIn('never regresses',r.stderr)

    def test_tdlib_dispatch_records_before_cache_delivery(self):
        source=(P/'org/thunderdog/challegram/telegram/Tdlib.java').read_text()
        for signature,hook in [('private void updateForumTopicInfo (','ForumRequests.onTopicInfo(this, update.info)'),('private void updateForumTopic (','ForumRequests.onTopicUpdate(this, update)')]:
            body=method(source,signature)
            self.assertIn(hook,body)
            self.assertLess(body.index(hook),body.index('listeners.'))

if __name__=='__main__':unittest.main()
