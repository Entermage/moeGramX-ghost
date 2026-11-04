"""Production arrow dispatch with bounded UI doubles; real taps are validated separately."""
from pathlib import Path
import unittest
from test_forum_scope import method
from test_forum_navigation_counters import run_java

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'app/src/main/java'
CONTROLLER=P/'org/thunderdog/challegram/ui/MessagesController.java'

HARNESS=r'''
import tgx.td.MessageId;import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;
public class ArrowHarness {
 static class Chat{long id=-100;}
 static class TGMessage{long chat,first,last;TGMessage(long c,long a,long b){chat=c;first=a;last=b;}long getChatId(){return chat;}long getBiggestId(){return last;}MessageId toMessageId(){return new MessageId(chat,last);}}
 static class Adapter{int indexOfMessageContainer(MessageId m){return -1;}}
 static class MessagesManager{
  static final int HIGHLIGHT_MODE_UNREAD=2,HIGHLIGHT_MODE_UNREAD_NEXT=4;static int groupLookups;
  static class DefaultAnchor{MessageId messageId=new MessageId(-100,1);int highlightMode=HIGHLIGHT_MODE_UNREAD;}
  static DefaultAnchor resolveDefaultAnchor(int account,Chat chat,Object thread){groupLookups++;return new DefaultAnchor();}
  static boolean canGoUnread(Chat c,Object t){return true;}static MessageId resolveUnreadAnchor(Chat c,Object t){return new MessageId(c.id,1);}
  TGMessage bottom,completeBottom;boolean returning;String action;long target;int count;
  boolean hasReturnMessage(){return returning;}TGMessage findBottomMessage(){return completeBottom!=null?completeBottom:bottom;}TGMessage findBottomMessage(boolean partial){return partial?bottom:findBottomMessage();}int indexOfFirstUnreadMessage(){return -1;}Adapter getAdapter(){return new Adapter();}
  void highlightMessage(MessageId id,int mode,Object unused,boolean smooth){action="unread";target=id.getMessageId();count++;}
  void resetByMessage(MessageId id,int mode){action="reset";target=id.getMessageId();count++;}
  void scrollToStart(boolean force){action=returning&&!force?"return":"latest";count++;}
 }
 Tdlib tdlib=new Tdlib();Chat chat=new Chat();Object messageThread;boolean topicMode=true,inPreviewMode,forceTouch;
 MessagesManager manager=new MessagesManager();TdApi.ForumTopic topic=new TdApi.ForumTopic();
 boolean xgramInForumTopic(){return topicMode&&messageThread==null;}boolean isInForceTouchMode(){return forceTouch;}
 TdApi.ForumTopic xgramTopicReadState(){return topic;}
 HELPER
 ARROW
 static int checks;static void check(boolean b,String msg){checks++;if(!b)throw new AssertionError(msg);}
 static ArrowHarness fixture(int unread,long read,long visible){ArrowHarness s=new ArrowHarness();s.topic.unreadCount=unread;s.topic.lastReadInboxMessageId=read;s.manager.bottom=new TGMessage(-100,visible,visible);return s;}
 static void click(ArrowHarness s,String action,long target){int before=s.manager.count;s.scrollToUnreadOrStartMessage();check(s.manager.count==before+1,"one navigation per tap");check(action.equals(s.manager.action),"expected "+action+" but got "+s.manager.action);if(target>=0)check(s.manager.target==target,"topic boundary only");}
 public static void main(String[] args){
  ArrowHarness s=fixture(0,500,100);click(s,"latest",-1);check(MessagesManager.groupLookups==0,"read topic never consults merged group unread state");
  s=fixture(70,500,100);click(s,"unread",500);s.manager.bottom=new TGMessage(-100,600,600);click(s,"latest",-1); // still-stale unread count
  s=fixture(70,500,500);click(s,"latest",-1);
  s=fixture(70,500,500);s.manager.completeBottom=new TGMessage(-100,450,450);click(s,"latest",-1);
  s=fixture(70,500,450);s.manager.bottom=new TGMessage(-100,450,520);click(s,"latest",-1); // album crosses the read boundary
  s=fixture(70,500,100);s.manager.returning=true;click(s,"return",-1);
  s=fixture(70,500,100);s.inPreviewMode=true;click(s,"latest",-1);
  s=fixture(70,500,100);s.forceTouch=true;click(s,"latest",-1);
  s=fixture(70,500,100);s.topic=null;click(s,"latest",-1);
  s=fixture(70,500,100);s.manager.bottom=null;click(s,"latest",-1);
  s=fixture(70,500,100);s.manager.bottom=new TGMessage(-200,100,100);click(s,"latest",-1);
  s=fixture(70,0,100);click(s,"latest",-1);
  check(MessagesManager.groupLookups==0,"all Topic cases avoid whole-group resolver");
  s=fixture(0,500,100);s.topicMode=false;click(s,"unread",1);check(MessagesManager.groupLookups==1,"ordinary chat still uses original policy");
  s=fixture(0,500,100);s.messageThread=new Object();click(s,"unread",1);check(MessagesManager.groupLookups==2,"comment threads keep original policy");
  System.out.println("PASS "+checks+" production arrow assertions");
 }
}'''

class ForumScrollLatestTests(unittest.TestCase):
    def harness(self,negative=None):
        source=CONTROLLER.read_text()
        arrow=method(source,'public void scrollToUnreadOrStartMessage (')
        helper=method(source,'private boolean scrollToForumUnreadOrStartMessage (')
        if negative=='group':arrow=arrow.replace('if (scrollToForumUnreadOrStartMessage()) return;','')
        if negative=='partial':helper=helper.replace('manager.findBottomMessage(true)','manager.findBottomMessage()')
        if negative=='loop':helper=helper.replace('bottom.getBiggestId() < unread.getMessageId()','true')
        anchor=method((P/'moe/kirao/mgx/topics/XgramForums.java').read_text(),'public static MessageId topicUnreadAnchor (')
        files={
          'ArrowHarness.java':HARNESS.replace('HELPER',helper).replace('ARROW',arrow),
          'tgx/td/MessageId.java':'''package tgx.td;public class MessageId{public static final long MIN_VALID_ID=1;long chat,id;public MessageId(long c,long i){chat=c;id=i;}public long getChatId(){return chat;}public long getMessageId(){return id;}}''',
          'org/thunderdog/challegram/telegram/Tdlib.java':'package org.thunderdog.challegram.telegram;public class Tdlib{public int id(){return 1;}}',
          'org/drinkless/tdlib/TdApi.java':'package org.drinkless.tdlib;public class TdApi{public static class ForumTopic{public int unreadCount;public long lastReadInboxMessageId;}}',
          'moe/kirao/mgx/topics/XgramForums.java':'''package moe.kirao.mgx.topics;import tgx.td.MessageId;import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;public class XgramForums{@interface Nullable {} static long topicReadInboxId(Tdlib t,long c,TdApi.ForumTopic v){return v.lastReadInboxMessageId;}'''+anchor+'}',
        }
        return run_java(files,'ArrowHarness')
    def test_topic_unread_latest_return_and_legacy_chat(self):
        r=self.harness();self.assertEqual(r.returncode,0,r.stderr)
    def test_negative_whole_group_boundary(self):
        r=self.harness('group');self.assertNotEqual(r.returncode,0);self.assertIn('expected latest',r.stderr)
    def test_negative_ignoring_partially_visible_read_message(self):
        r=self.harness('partial');self.assertNotEqual(r.returncode,0);self.assertIn('expected latest',r.stderr)
    def test_negative_repeated_unread_loop(self):
        r=self.harness('loop');self.assertNotEqual(r.returncode,0);self.assertIn('expected latest',r.stderr)

if __name__=='__main__':unittest.main()
