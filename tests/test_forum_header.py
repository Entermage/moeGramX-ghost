"""Run the production topic title handoff and async header bindings with controlled metadata."""
from pathlib import Path
import unittest
from test_forum_scope import method
from test_forum_navigation_counters import run_java

P = Path(__file__).resolve().parents[1] / 'app/src/main/java'

HARNESS = r'''
import java.util.*;
public class HeaderHarness {
 @interface Nullable {}
 interface FutureInt {int getIntValue();}
 interface RunnableData<T> {void runWithData(T value);}
 static class TdApi {
  static class Chat {long id=7;}
  static class MessageTopic {}
  static class MessageTopicForum extends MessageTopic {int forumTopicId;MessageTopicForum(int i){forumTopicId=i;}}
  static class ForumTopicInfo {long chatId;int forumTopicId;String name;ForumTopicInfo(long c,int i,String n){chatId=c;forumTopicId=i;name=n;}}
  static class ForumTopic {ForumTopicInfo info;Object draftMessage;ForumTopic(ForumTopicInfo i){info=i;}}
  static class GetForumTopic {long chatId;int id;GetForumTopic(long c,int i){chatId=c;id=i;}}
 }
 static class Td {static boolean isEmpty(Object x){return x==null;}}
 static class StringUtils {static boolean isEmpty(String s){return s==null||s.isEmpty();}}
 static class R {static class string {static int XgramTopicInChat=1,General=2;}}
 static class Lang {static String getString(int id,Object... v){return v.length==0?"General":"in "+v[0];}}
 static class TdlibForumTopicManager {static class Key {Key(long c,int t){}}}
 static class Entry {TdApi.ForumTopic value;Entry(TdApi.ForumTopic v){value=v;}}
 interface Lookup {void result(Entry entry,boolean inPlace);}
 static class Topics {List<Lookup> pending=new ArrayList<>();void findOrRequest(TdlibForumTopicManager.Key k,Lookup callback){pending.add(callback);}}
 static class Ui {
  TdlibUi.ChatOpenParameters opened;
  void post(Runnable r){r.run();}
  void openChat(TdlibDelegate c,TdApi.Chat chat,TdlibUi.ChatOpenParameters p){opened=p;}
 }
 static class Tdlib {Ui ui=new Ui();Topics topics=new Topics();Ui ui(){return ui;}Topics topics(){return topics;}String chatTitle(TdApi.Chat c){return "Group";}}
 interface TdlibDelegate {Tdlib tdlib();}
 static class ViewController<T> implements TdlibDelegate {
  Tdlib tdlib=new Tdlib();TdApi.Chat chat=new TdApi.Chat();boolean destroyed;
  public Tdlib tdlib(){return tdlib;}boolean isDestroyed(){return destroyed;}long getChatId(){return chat.id;}
 }
 static class ChatHeaderView {String title="Group",subtitle;void setTitle(String s){title=s;}void setForcedSubtitle(String s){subtitle=s;}void xgramSetStatusTopic(long c,Object t){}}
 static class TdlibUi {
  static class UrlOpenParameters {}
  static class ChatOpenParameters {Object messageTopicId;String forumTopicTitle;ChatOpenParameters keepStack(){return this;}ChatOpenParameters urlOpenParameters(Object x){return this;}void highlightMessage(int m,Object a){}}
 }
 static class TopicResume {int highlightMode;Object anchor;}
 static class ForumTopicList {static TdApi.ForumTopic cached;static TdApi.ForumTopic peekTopic(Tdlib t,long c,int i){return cached;}}
 static class ForumTopicCounters {static TdApi.ForumTopic copy(TdApi.ForumTopic t){return t;}static TdApi.ForumTopic mergeSnapshot(TdApi.ForumTopic a,TdApi.ForumTopic b,boolean changed){return b;}}
 static class XgramTopicReadOutbox {static void set(Tdlib t,long c,TdApi.ForumTopic f){}}
 static class XgramTopicMute {static void onSettings(Tdlib t,long c,TdApi.ForumTopic f){}}
 interface Response {void result(TdApi.ForumTopic topic,Object error);}
 static class ForumRequests {static List<Response> pending=new ArrayList<>();static void send(Tdlib t,Object o,TdApi.GetForumTopic q,Response r){pending.add(r);}}
 static class XgramForums {
  static String topicTitle(TdApi.ForumTopicInfo i){return i.name;}
  static TopicResume topicResume(Tdlib t,long c,int i,TdApi.ForumTopic f){return new TopicResume();}
  static boolean isTopicClosedForMe(Tdlib t,TdApi.Chat c,TdApi.ForumTopicInfo i){return false;}
  static TdApi.ForumTopic normalizedCopy(Tdlib t,TdApi.ForumTopic f){return f;}
  OPEN
  BIND
 }
 static class Icon {void set(Tdlib t,Object i){}void clear(){}}
 static class Manager {void viewMessages(boolean b){}}
 static class Controller extends ViewController<Object> {
  static final int PREVIEW_MODE_NONE=0;
  Object messageThread;TdApi.MessageTopic messageTopicId;int previewMode;String xgramTopicTitle;
  ChatHeaderView headerCell=new ChatHeaderView();Icon xgramTopicIcon;Manager manager=new Manager();
  TdApi.ForumTopic xgramForumTopic;long xgramTopicCounterRevision,xgramTopicBindingGeneration;
  boolean xgramTopicClosedForMe,xgramTopicLoading,xgramTopicRefreshAgain;
  boolean xgramInForumTopic(){return messageThread==null&&messageTopicId instanceof TdApi.MessageTopicForum;}
  int xgramCurrentTab(){return xgramInForumTopic()?((TdApi.MessageTopicForum)messageTopicId).forumTopicId:0;}
  Icon xgramTopicIcon(){if(xgramTopicIcon==null)xgramTopicIcon=new Icon();return xgramTopicIcon;}
  void xgramCancelTopicRefresh(){xgramTopicBindingGeneration++;xgramTopicLoading=false;}
  void updateBottomBar(boolean b){}void xgramUpdateTabs(){}void xgramApplyTopicCounters(boolean b){}
  boolean isFocused(){return true;}void runOnUiThreadOptional(Runnable r){r.run();}
  void xgramApplyTopicReadOutbox(){}void xgramApplyTopicDraft(Object d){}void xgramScheduleTopicRefresh(){}
  CONTROLLER_BIND
  SET_INFO
  LOAD
 }
 static class Arguments {
  Object messageThread,messageTopicId;boolean inPreviewMode;String forumTopicTitle;
  ARGUMENT
 }
 static int checks;
 static void check(boolean b,String m){checks++;if(!b)throw new AssertionError(m);}
 static TdApi.ForumTopic topic(long chat,int id,String title){return new TdApi.ForumTopic(new TdApi.ForumTopicInfo(chat,id,title));}
 public static void main(String[] argv){
  Controller c=new Controller();TdApi.ForumTopic selected=topic(7,9,"Selected topic");
  XgramForums.openTopic(c,c.chat,selected,null);
  TdlibUi.ChatOpenParameters params=c.tdlib.ui.opened;
  check("Selected topic".equals(params.forumTopicTitle),"selected title lost before navigation");
  Arguments a=new Arguments();a.messageTopicId=params.messageTopicId;a.setForumTopicTitle(params.forumTopicTitle);
  c.messageTopicId=(TdApi.MessageTopic)a.messageTopicId;c.xgramTopicTitle=a.forumTopicTitle;
  ForumTopicList.cached=null;c.xgramBindTopicHeader();
  check(c.headerCell.title.equals("Selected topic"),"released list cannot erase selected title");
  ForumRequests.pending.get(0).result(null,new Object());c.tdlib.topics.pending.get(0).result(new Entry(null),true);
  check(c.headerCell.title.equals("Selected topic"),"metadata failure retains selected title");
  c.xgramLoadTopic();ForumRequests.pending.get(1).result(topic(7,9,"Refreshed name"),null);
  check(c.headerCell.title.equals("Refreshed name"),"successful main metadata refresh must update header");
  c.xgramSetTopicInfo(topic(7,9,"Renamed").info);check(c.headerCell.title.equals("Renamed"),"live rename applies");
  c.xgramSetTopicInfo(topic(8,9,"Wrong group").info);c.xgramSetTopicInfo(topic(7,10,"Wrong topic").info);
  check(c.headerCell.title.equals("Renamed"),"foreign metadata must not overwrite header");
  // A late response to the first binding cannot rename the controller after a topic switch.
  c.messageTopicId=new TdApi.MessageTopicForum(10);c.xgramTopicTitle="Next topic";c.xgramBindTopicHeader();
  c.tdlib.topics.pending.get(0).result(new Entry(topic(7,9,"Stale")),false);
  ForumRequests.pending.get(1).result(topic(7,9,"Stale main"),null);
  check(c.headerCell.title.equals("Next topic"),"late prior binding cannot rename next topic");
  c.tdlib.topics.pending.get(1).result(new Entry(topic(7,10,"Fresh next")),false);
  check(c.headerCell.title.equals("Fresh next"),"separate metadata lookup updates title");
  c.destroyed=true;c.tdlib.topics.pending.get(1).result(new Entry(topic(7,10,"Destroyed")),false);
  check(c.headerCell.title.equals("Fresh next"),"destroyed callback ignored");
  for(int mode=0;mode<3;mode++){
   a=new Arguments();a.messageTopicId=mode==0?null:new TdApi.MessageTopicForum(9);a.messageThread=mode==1?new Object():null;a.inPreviewMode=mode==2;
   a.setForumTopicTitle("Should not appear");check(a.forumTopicTitle==null,"ordinary/comment/preview isolation");
  }
  System.out.println(checks+" production topic title checks passed");
 }
}
'''

class ForumHeaderTests(unittest.TestCase):
    def run_header(self, negative=None):
        forums=(P/'moe/kirao/mgx/topics/XgramForums.java').read_text()
        controller=(P/'org/thunderdog/challegram/ui/MessagesController.java').read_text()
        pieces={
          'OPEN':method(forums,'private static void openTopic (TdlibDelegate context, TdApi.Chat chat, TdApi.ForumTopic topic,'),
          'BIND':method(forums,'public static void bindTopicHeader ('),
          'CONTROLLER_BIND':method(controller,'private void xgramBindTopicHeader ('),
          'SET_INFO':method(controller,'private void xgramSetTopicInfo ('),
          'LOAD':method(controller,'private void xgramLoadTopic ('),
          'ARGUMENT':method(controller,'public Arguments setForumTopicTitle (')}
        if negative=='seed':pieces['OPEN']=pieces['OPEN'].replace('params.forumTopicTitle = topicTitle(topic.info);','')
        if negative=='refresh':pieces['LOAD']=pieces['LOAD'].replace('xgramSetTopicInfo(xgramForumTopic.info);','')
        code=HARNESS
        for k,v in pieces.items():code=code.replace('\n  '+k+'\n','\n'+v.replace('moe.kirao.mgx.topics.','')+'\n')
        return run_java({'HeaderHarness.java':code},'HeaderHarness')

    def test_handoff_errors_refresh_and_isolation(self):
        r=self.run_header();self.assertEqual(r.returncode,0,r.stderr)
    def test_negative_missing_navigation_title(self):
        r=self.run_header('seed');self.assertNotEqual(r.returncode,0);self.assertIn('selected title lost',r.stderr)
    def test_negative_main_metadata_does_not_refresh_title(self):
        r=self.run_header('refresh');self.assertNotEqual(r.returncode,0);self.assertIn('main metadata refresh',r.stderr)

if __name__=='__main__':unittest.main()
