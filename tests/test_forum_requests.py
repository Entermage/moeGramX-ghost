"""Exercise the production metadata queue with a controllable Android/TDLib clock."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/moe/kirao/mgx/topics/ForumRequests.java'

STUBS = {
'org/drinkless/tdlib/TdApi.java': '''package org.drinkless.tdlib;
public class TdApi {
 public static class Object {}
 public static class Function<T extends Object> extends Object {}
 public static class Error extends Object {public int code;public String message;public Error(int c,String m){code=c;message=m;}}
 public static class MessageTopicForum {public int forumTopicId;public MessageTopicForum(int id){forumTopicId=id;}}
 public static class Message {public long id,chatId;public java.lang.Object topicId;public Message(long id){this.id=id;}}
 public static class ForumTopicInfo extends Object {public long chatId;public int forumTopicId;public String name;public ForumTopicInfo(long c,int i,String n){chatId=c;forumTopicId=i;name=n;}}
 public static class DraftMessage extends Object {public int date;public String text;public DraftMessage(int d,String t){date=d;text=t;}}
 public static class ChatNotificationSettings extends Object {public int muteFor;public boolean useDefaultMuteFor;public ChatNotificationSettings(int m){muteFor=m;}}
 public static class UpdateForumTopic extends Object {public long chatId,lastReadInboxMessageId,lastReadOutboxMessageId;public int forumTopicId,unreadMentionCount,unreadReactionCount,unreadPollVoteCount;public boolean isPinned;public ChatNotificationSettings notificationSettings;public DraftMessage draftMessage;}
 public static class ForumTopic extends Object {public ForumTopicInfo info;public Message lastMessage;public long order,lastReadInboxMessageId,lastReadOutboxMessageId;public boolean isPinned;public int unreadCount,unreadMentionCount,unreadReactionCount,unreadPollVoteCount;public ChatNotificationSettings notificationSettings;public DraftMessage draftMessage;
 public ForumTopic(){}
 public ForumTopic(ForumTopicInfo i,Message m,long o,boolean p,int u,long read,long out,int mentions,int reactions,int polls,ChatNotificationSettings settings,DraftMessage draft){info=i;lastMessage=m;order=o;isPinned=p;unreadCount=u;lastReadInboxMessageId=read;lastReadOutboxMessageId=out;unreadMentionCount=mentions;unreadReactionCount=reactions;unreadPollVoteCount=polls;notificationSettings=settings;draftMessage=draft;}}
 public static class ForumTopics extends Object {public int totalCount,nextOffsetDate,nextOffsetForumTopicId;public long nextOffsetMessageId;public ForumTopic[] topics;public ForumTopics(int total,ForumTopic[] rows,int d,long m,int t){totalCount=total;topics=rows;nextOffsetDate=d;nextOffsetMessageId=m;nextOffsetForumTopicId=t;}}
 public static class GetForumTopic extends Function<ForumTopic> {public long chatId;public int forumTopicId;public GetForumTopic(long c,int t){chatId=c;forumTopicId=t;}}
 public static class GetForumTopics extends Function<ForumTopics> {public long chatId,offsetMessageId;public int offsetDate,offsetForumTopicId,limit;public String query="";public GetForumTopics(){} public GetForumTopics(long c,String q,int d,long m,int t,int l){chatId=c;query=q;offsetDate=d;offsetMessageId=m;offsetForumTopicId=t;limit=l;}}
}''',
'org/thunderdog/challegram/tool/UI.java': '''package org.thunderdog.challegram.tool;
public class UI {public static boolean inUiThread(){return true;}}''',
'androidx/annotation/Keep.java': '''package androidx.annotation; public @interface Keep {}''',
'org/thunderdog/challegram/telegram/Tdlib.java': '''package org.thunderdog.challegram.telegram;
import org.drinkless.tdlib.TdApi; import java.util.*;
public class Tdlib {
 public interface ResultHandler<T extends TdApi.Object>{void onResult(T value,TdApi.Error error);}
 public static final class Clock {
  public long now; private long sequence;
  static class Job {long at,seq;Runnable task;Job(long a,long s,Runnable r){at=a;seq=s;task=r;}}
  ArrayList<Job> jobs=new ArrayList<>();
  public void post(Runnable r){postDelayed(r,0);}
  public void postDelayed(Runnable r,long ms){jobs.add(new Job(now+ms,sequence++,r));}
  public void removeCallbacks(Runnable r){jobs.removeIf(j->j.task==r);}
  public void advance(long ms){long end=now+ms;int guard=0;while(true){Job next=jobs.stream().filter(j->j.at<=end).min(Comparator.comparingLong((Job j)->j.at).thenComparingLong(j->j.seq)).orElse(null);if(next==null)break;if(++guard>10000)throw new AssertionError("busy loop");jobs.remove(next);now=next.at;next.task.run();}now=end;}
 }
 public static class Call {public TdApi.Function<?> query;public ResultHandler<TdApi.Object> handler;Call(TdApi.Function<?>q,ResultHandler<TdApi.Object>h){query=q;handler=h;}}
 public final Clock clock=new Clock();public final ArrayList<Call> calls=new ArrayList<>();
 public Clock ui(){return clock;}
 @SuppressWarnings("unchecked") public <T extends TdApi.Object> void send(TdApi.Function<T>q,ResultHandler<T>h){calls.add(new Call(q,(ResultHandler<TdApi.Object>)(ResultHandler<?>)h));}
 public void finish(int index){calls.get(index).handler.onResult(new TdApi.ForumTopic(),null);clock.advance(0);}
}''',
'moe/kirao/mgx/topics/XgramTopicFlood.java': '''package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;import java.util.*;
public class XgramTopicFlood {static final Map<Tdlib,Long> until=new IdentityHashMap<>();
 public static long waitMs(Tdlib t){return Math.max(0,until.getOrDefault(t,0L)-t.clock.now);}
 public static long onError(Tdlib t,TdApi.Error e,long fallback){if(e.code==429)until.put(t,t.clock.now+90000);return fallback;}
}''',
'moe/kirao/mgx/topics/QueueHarness.java': '''package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;
public class QueueHarness {
 static int checks;static void check(boolean v,String msg){checks++;if(!v)throw new AssertionError(msg);}
 static void request(Tdlib t,Object owner,int id){ForumRequests.send(t,owner,new TdApi.GetForumTopic(-100,id),(r,e)->{});}
 public static void main(String[] args){
  Tdlib t=new Tdlib();Object owner=new Object();int[] delivered={0};
  for(int i=0;i<100;i++)ForumRequests.send(t,owner,new TdApi.GetForumTopic(-100,1),(r,e)->{if(r!=null)delivered[0]++;});
  check(t.calls.size()==1,"100 duplicate reads must coalesce");t.finish(0);check(delivered[0]==1,"latest callback only per owner");
  for(int i=2;i<70;i++)request(t,new Object(),i);
  long[] s=ForumRequests.snapshot(t);check(s[0]==2,"native concurrency");check(s[1]==24,"queue limit");check(s[8]>0,"overflow is explicit");
  int sent=t.calls.size();t.clock.advance(31000);check(ForumRequests.snapshot(t)[0]==2,"timeout retains native slots");check(ForumRequests.snapshot(t)[1]==0,"queued timeouts removed");
  for(int minute=0;minute<10;minute++){for(int i=0;i<60;i++)request(t,owner,2);t.clock.advance(60000);check(t.calls.size()==sent,"ten-minute native accumulation");}
  t.finish(1);check(ForumRequests.snapshot(t)[0]==1,"actual callback releases one slot");request(t,owner,80);check(t.calls.size()==sent+1,"recovery after real callback");
  Tdlib cancel=new Tdlib();Object screen=new Object();for(int i=0;i<15;i++)request(cancel,screen,i);check(cancel.calls.size()==2,"two active at most");ForumRequests.cancel(cancel,screen);check(ForumRequests.snapshot(cancel)[1]==0,"close removes queue");cancel.finish(0);cancel.finish(1);cancel.clock.advance(120000);check(cancel.calls.size()==2,"no work after close");
  Tdlib a=new Tdlib(),b=new Tdlib();request(a,screen,1);request(b,screen,1);check(a.calls.size()==1&&b.calls.size()==1,"account isolation");ForumRequests.onClientClosed(a);request(a,screen,2);a.finish(0);check(ForumRequests.snapshot(a)[0]==1,"late closed-client callback cannot release new request");
  Tdlib flood=new Tdlib();XgramTopicFlood.until.put(flood,90000L);request(flood,screen,1);flood.clock.advance(29000);check(flood.calls.isEmpty(),"FLOOD_WAIT before deadline");flood.clock.advance(62000);check(flood.calls.isEmpty(),"expired queue not resurrected after FLOOD_WAIT");request(flood,screen,2);check(flood.calls.size()==1,"demand resumes after wait");
  Tdlib shared=new Tdlib();int[] got={0};Object s1=new Object(),s2=new Object();ForumRequests.send(shared,s1,new TdApi.GetForumTopic(-1,3),(r,e)->got[0]++);ForumRequests.send(shared,s2,new TdApi.GetForumTopic(-1,3),(r,e)->got[0]+=10);ForumRequests.cancel(shared,s1);shared.finish(0);check(got[0]==10,"closing one observer preserves other observer");
  System.out.println("PASS "+checks+" production queue assertions");
 }
}'''
}

class ForumRequestTests(unittest.TestCase):
    def compile_run(self, source):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = dict(STUBS)
            files['moe/kirao/mgx/topics/ForumRequests.java'] = source
            files['moe/kirao/mgx/topics/ForumTopicSnapshotUpdates.java'] = (SOURCE.parent / 'ForumTopicSnapshotUpdates.java').read_text()
            for name, text in files.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            subprocess.run(['javac','-d',str(root/'out'),*[str(root/p) for p in files]],check=True,capture_output=True,text=True)
            return subprocess.run(['java','-cp',str(root/'out'),'moe.kirao.mgx.topics.QueueHarness'],capture_output=True,text=True)

    def test_production_queue_lifecycle_and_bounds(self):
        result=self.compile_run(SOURCE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('production queue assertions',result.stdout)

    def test_negative_control_catches_native_limit_removed(self):
        result=self.compile_run(SOURCE.read_text().replace('MAX_NATIVE = 2','MAX_NATIVE = 100'))
        self.assertNotEqual(result.returncode,0)
        self.assertIn('native concurrency',result.stderr)

    def test_negative_control_catches_early_timeout_release(self):
        text=SOURCE.read_text().replace('entry.expired = true;', 'entry.expired = true; if (entry.active) state.nativeCount--;')
        result=self.compile_run(text)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('timeout retains native slots',result.stderr)

if __name__ == '__main__': unittest.main()
