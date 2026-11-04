"""Production return snapshots, topic badge math and leading refresh deadline."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_forum_scope import method
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'app/src/main/java'

def run_java(files, main):
    with tempfile.TemporaryDirectory() as tmp:
        for name,code in files.items():
            p=Path(tmp)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(code)
        result=subprocess.run(['javac','-d',tmp,*[str(Path(tmp)/n) for n in files]],capture_output=True,text=True)
        if result.returncode: raise AssertionError(result.stderr)
        return subprocess.run(['java','-cp',tmp,main],capture_output=True,text=True)

NAV=r"""
import java.util.*;
public class NavHarness {
  static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
  static class ForumRequests {static void cancel(Object t,Object o){}}
  static class Topic {int id;Topic(int n){id=n;}}
  static class ForumTopicList {
    static ForumTopicList cached;Object tdlib;long chatId;List<Topic> topics=new ArrayList<>();List<Object> listeners=new ArrayList<>();
    int nextOffsetDate,nextOffsetForumTopicId,localReorderVersion;long nextOffsetMessageId,lastResyncAt,lastReturnRefreshAt,loadRetryAfter;
    boolean endReached,isLoaded,generalChecked,loadFailed,isLoading,isDestroyed;int[] pins={};int requests;
    ForumTopicList(Object tdlib,long chatId){this.tdlib=tdlib;this.chatId=chatId;}
    static ForumTopicList obtain(Object t,long c){if(cached==null||cached.isDestroyed)cached=new ForumTopicList(t,c);return cached;}
    int[] pinnedTopicIds(){return pins.clone();}void replacePinnedOrder(int[] p){pins=p;}
    void addListener(Object o){listeners.add(o);}void removeListener(Object o){listeners.remove(o);if(listeners.isEmpty())isDestroyed=true;}
    boolean isLoaded(){return isLoaded;}void loadMore(){requests++;isLoading=true;}
    RESTORE
  }
  static class Args {Chat chat=new Chat();}static class Chat {long id=7;}
  ForumTopicList list;boolean listAttached;Object tdlib=new Object();Args args=new Args();
  Args getArgumentsStrict(){return args;}void cancelPendingSearch(){}
  ENSURE
  RELEASE
  NEED
  private void cancelSearchRequests(){ cancelPendingSearch(); ForumRequests.cancel(tdlib,this); }
  public static void main(String[] argv){
    NavHarness screen=new NavHarness();screen.ensureList();check(!screen.needAsynchronousAnimation(),"first opening starts without waiting for initial data");
    ForumTopicList loaded=screen.list;loaded.isLoaded=true;loaded.isLoading=false;loaded.topics.add(new Topic(9));loaded.nextOffsetDate=50;loaded.nextOffsetMessageId=500;loaded.nextOffsetForumTopicId=9;loaded.loadRetryAfter=8000;loaded.pins=new int[]{9};
    screen.releaseList();check(loaded.isDestroyed&&loaded.listeners.isEmpty(),"covered list releases work");
    check(screen.list!=null&&screen.list.topics.size()==1,"rows survive covering without waiting for network");
    screen.ensureList(); // onFocus reattaches data independently of animation readiness
    check(!screen.needAsynchronousAnimation(),"return must not wait for network");
    check(screen.list!=loaded&&screen.list.requests==0,"return restores display data without request barrier");
    check(screen.list.nextOffsetMessageId==500&&screen.list.nextOffsetForumTopicId==9&&screen.list.pins[0]==9,"pagination and pinned order survive");
    check(screen.list.loadRetryAfter==8000,"return preserves retry backoff");
    ForumTopicList wrong=new ForumTopicList(new Object(),7);wrong.restoreFrom(loaded);check(!wrong.isLoaded,"snapshot cannot cross accounts");
    wrong=new ForumTopicList(screen.tdlib,8);wrong.restoreFrom(loaded);check(!wrong.isLoaded,"snapshot cannot cross chats");
    for(int i=0;i<20;i++){screen.releaseList();screen.ensureList();check(!screen.needAsynchronousAnimation(),"repeated back retains rows");check(screen.list.requests==0,"offline returns do not reload");}
    System.out.println("return lifecycle checks passed");
  }
}
"""

API=r"""
package org.drinkless.tdlib;
public class TdApi {
 public static class MessageTopicForum {public int forumTopicId;public MessageTopicForum(int id){forumTopicId=id;}}
 public static class Message {public long id,chatId;public boolean isOutgoing;public Object topicId,schedulingState;public Message(long id,long chat,int topic,boolean outgoing){this.id=id;chatId=chat;topicId=new MessageTopicForum(topic);isOutgoing=outgoing;}}
 public static class Info {public long chatId;public int forumTopicId;public Info(long c,int t){chatId=c;forumTopicId=t;}}
 public static class ForumTopic {public Info info;public Message lastMessage;public long order,lastReadInboxMessageId,lastReadOutboxMessageId;public boolean isPinned;public int unreadCount,unreadMentionCount,unreadReactionCount,unreadPollVoteCount;public Object notificationSettings,draftMessage;
 public ForumTopic(Info i,Message m,long o,boolean p,int u,long read,long out,int mentions,int reactions,int polls,Object settings,Object draft){info=i;lastMessage=m;order=o;isPinned=p;unreadCount=u;lastReadInboxMessageId=read;lastReadOutboxMessageId=out;unreadMentionCount=mentions;unreadReactionCount=reactions;unreadPollVoteCount=polls;notificationSettings=settings;draftMessage=draft;}}
}
"""
COUNT=r"""
import org.drinkless.tdlib.TdApi;
import moe.kirao.mgx.topics.ForumTopicCounters;
public class CountHarness {
 static class TGMessage {TdApi.Message[] messages;boolean fake,sponsored;TGMessage(TdApi.Message... m){messages=m;}boolean isFakeMessage(){return fake;}boolean isSponsoredMessage(){return sponsored;}long getBiggestId(){long id=0;for(TdApi.Message m:messages)id=Math.max(id,m.id);return id;}TdApi.Message[] getAllMessages(){return messages;}}
 static class Adapter {TGMessage[] rows;TGMessage getMessage(int i){return rows[i];}}
 static class Loader {boolean more;boolean canLoadBottom(){return more;}}
 Adapter adapter=new Adapter();Loader loader=new Loader();int getActiveMessageCount(){return adapter.rows.length;}
 COUNT
 static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
 static TdApi.Message msg(long id,int topic,boolean outgoing){return new TdApi.Message(id,7,topic,outgoing);}
 static TdApi.ForumTopic topic(long read,int count){return new TdApi.ForumTopic(new TdApi.Info(7,9),msg(900,9,false),0,false,count,read,0,0,0,0,null,null);}
 public static void main(String[] args){
  CountHarness h=new CountHarness();
  h.adapter.rows=new TGMessage[]{new TGMessage(msg(900,9,false)),new TGMessage(msg(850,9,true)),new TGMessage(msg(800,9,false),msg(700,9,false)),new TGMessage(msg(650,10,false)),new TGMessage(msg(600,9,false)),new TGMessage(msg(100,9,false))};
  TdApi.ForumTopic t=topic(100,5);
  check(h.forumUnreadAfterRead(t,600)==3,"remaining count uses individual album items and excludes other topic/outgoing");
  check(h.forumUnreadAfterRead(t,800)==1,"partial scroll decrements badge immediately");
  check(h.forumUnreadAfterRead(t,900)==0,"bottom clears badge");
  h.loader.more=true;t.unreadCount=20;
  check(h.forumUnreadAfterRead(t,800)==17,"incomplete history subtracts loaded incoming IDs, not gaps between IDs");
  check(h.forumUnreadAfterRead(t,100)==20,"repeated reading does not subtract twice");
  TdApi.ForumTopic local=topic(800,1),stale=topic(100,8);
  TdApi.ForumTopic merged=ForumTopicCounters.mergeSnapshot(local,stale,false);
  check(merged.lastReadInboxMessageId==800&&merged.unreadCount==1,"stale snapshot must not undo local read");
  check(stale.lastReadInboxMessageId==100&&local.unreadCount==1,"snapshots do not mutate shared topic objects");
  check(ForumTopicCounters.mergeSnapshot(local,topic(800,4),true).unreadCount==1,"in-flight result cannot overwrite newer badge");
  check(ForumTopicCounters.mergeSnapshot(local,topic(900,0),true).unreadCount==0,"newer server read is accepted");
  TdApi.ForumTopic other=topic(100,4);other.info.forumTopicId=10;check(ForumTopicCounters.mergeSnapshot(local,other,true).unreadCount==4,"topic isolation");
  local.lastMessage=msg(1000,9,false);check(ForumTopicCounters.mergeSnapshot(local,stale,true).lastMessage.id==1000,"new message during request retained");
  TdApi.Message scheduled=msg(950,9,false);scheduled.schedulingState=new Object();check(!ForumTopicCounters.isIncomingAfter(scheduled,7,9,100),"scheduled messages excluded");
  System.out.println("topic badge checks passed");
 }
}
"""
SCHEDULE=r"""
import java.util.*;
public class ScheduleHarness {
 static class Handler {long now,at;Runnable job;int posts;void postDelayed(Runnable r,long delay){job=r;at=now+delay;posts++;}void removeCallbacks(Runnable r){if(job==r)job=null;}void advance(long ms){now+=ms;if(job!=null&&at<=now){Runnable r=job;job=null;r.run();}}}
 static class Tdlib {Handler h=new Handler();Handler ui(){return h;}}
 Tdlib tdlib=new Tdlib();boolean xgramTopicLoading,xgramTopicRefreshAgain,xgramTopicRefreshScheduled;boolean focused=true,destroyed;int sent;
 boolean isDestroyed(){return destroyed;}boolean isFocused(){return focused;}boolean xgramInForumTopic(){return true;}
 Runnable xgramTopicRefresh=()->{xgramTopicRefreshScheduled=false;sent++;};
 SCHEDULE
 static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
 public static void main(String[] args){ScheduleHarness h=new ScheduleHarness();for(int i=0;i<15;i++){h.xgramScheduleTopicRefresh();h.tdlib.h.advance(100);}check(h.sent==1,"continuous messages cannot starve refresh");check(h.tdlib.h.posts==1,"burst produces one deadline");h.xgramTopicLoading=true;for(int i=0;i<100;i++)h.xgramScheduleTopicRefresh();check(h.xgramTopicRefreshAgain&&h.tdlib.h.posts==1,"active request retains only one follow-up");h.xgramTopicLoading=false;h.focused=false;h.xgramScheduleTopicRefresh();check(h.tdlib.h.posts==1,"offscreen schedules no work");System.out.println("refresh deadline checks passed");}
}
"""

class ForumNavigationCounterTest(unittest.TestCase):
    def nav(self,negative=False):
        c=(P/'moe/kirao/mgx/topics/ForumTopicsController.java').read_text();l=(P/'moe/kirao/mgx/topics/ForumTopicList.java').read_text()
        s=NAV.replace('RESTORE',method(l,'public void restoreFrom (')).replace('ENSURE',method(c,'private ForumTopicList ensureList (')).replace('RELEASE',method(c,'private void releaseList (')).replace('NEED',method(c,'public boolean needAsynchronousAnimation ('))
        if negative:s=s.replace('list.restoreFrom(previous);','')
        return run_java({'NavHarness.java':s},'NavHarness')
    def counts(self,negative=False):
        helper=(P/'moe/kirao/mgx/topics/ForumTopicCounters.java').read_text()
        if negative:helper=helper.replace('received.lastReadInboxMessageId < current.lastReadInboxMessageId','false')
        scope=method((P/'moe/kirao/mgx/topics/XgramForums.java').read_text(),'public static boolean isInTopic (')
        manager=method((P/'org/thunderdog/challegram/component/chat/MessagesManager.java').read_text(),'public int forumUnreadAfterRead (')
        return run_java({'org/drinkless/tdlib/TdApi.java':API,'moe/kirao/mgx/topics/ForumTopicCounters.java':helper,'moe/kirao/mgx/topics/XgramForums.java':'package moe.kirao.mgx.topics;import org.drinkless.tdlib.TdApi;public class XgramForums {static final int GENERAL_TOPIC_ID=1;'+scope+'}','CountHarness.java':COUNT.replace('COUNT',manager)},'CountHarness')
    def schedule(self,negative=False):
        method_code=method((P/'org/thunderdog/challegram/ui/MessagesController.java').read_text(),'private void xgramScheduleTopicRefresh (')
        if negative:method_code=method_code.replace('if (xgramTopicRefreshScheduled) return;','tdlib.ui().removeCallbacks(xgramTopicRefresh);')
        return run_java({'ScheduleHarness.java':SCHEDULE.replace('SCHEDULE',method_code)},'ScheduleHarness')
    def test_return_preserves_rows_without_network(self):
        result=self.nav();self.assertEqual(result.returncode,0,result.stderr)
    def test_negative_dropped_return_snapshot(self):
        result=self.nav(True);self.assertNotEqual(result.returncode,0);self.assertIn('return restores display data without request barrier',result.stderr)
    def test_unread_partial_bottom_album_and_races(self):
        result=self.counts();self.assertEqual(result.returncode,0,result.stderr)
    def test_negative_stale_read_rollback(self):
        result=self.counts(True);self.assertNotEqual(result.returncode,0);self.assertIn('stale snapshot',result.stderr)
    def test_refresh_does_not_starve_or_poll(self):
        result=self.schedule();self.assertEqual(result.returncode,0,result.stderr)
    def test_negative_trailing_debounce(self):
        result=self.schedule(True);self.assertNotEqual(result.returncode,0);self.assertIn('cannot starve',result.stderr)

if __name__=='__main__':unittest.main()
