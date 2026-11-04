"""Service messages must not treat a cached metadata error as usable topic information."""
from pathlib import Path
import unittest
from test_forum_scope import method
from test_forum_navigation_counters import run_java

P=Path(__file__).resolve().parents[1]/'app/src/main/java/org/thunderdog/challegram/data/TGMessage.java'

HARNESS=r'''
import java.util.*;
public class InfoHarness {
 interface RunnableBool {void runWithBool(boolean inPlace);}
 static class TdApi {static class ForumTopicInfo {String name="Topic";}}
 static class TdlibForumTopicManager {static class Entry {boolean error;}}
 static class Topics {
  int registered,mode;InfoHarness observer;
  TdlibForumTopicManager.Entry findAndObserve(Object key,InfoHarness h){
   registered++;observer=h;
   if(mode==1){h.setTopicInfo(new TdApi.ForumTopicInfo());return new TdlibForumTopicManager.Entry();}
   if(mode==2){TdlibForumTopicManager.Entry error=new TdlibForumTopicManager.Entry();error.error=true;return error;}
   return null;
  }
 }
 static class Tdlib {Topics topics=new Topics();Topics topics(){return topics;}}
 Object forumTopicKey=new Object();boolean topicObserverRegistered;TdApi.ForumTopicInfo topicInfo;
 List<RunnableBool> postponedTopicInfoCallbacks;Tdlib tdlib=new Tdlib();int calls,updates;
 void onTopicInfoUpdated(){updates++;}
 WITH
 SET
 GET
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 void ready(boolean inPlace){check(topicInfo().name.equals("Topic"),"only actual metadata enables named text");calls++;}
 public static void main(String[] args){
  InfoHarness cachedError=new InfoHarness();cachedError.tdlib.topics.mode=2;cachedError.withTopicInfo(cachedError::ready);
  check(cachedError.calls==0,"cached error must retain generic service text");
  cachedError.withTopicInfo(cachedError::ready);check(cachedError.tdlib.topics.registered==1,"one observer per message");
  cachedError.setTopicInfo(new TdApi.ForumTopicInfo());check(cachedError.calls==2,"both pending users recover once");
  check(cachedError.postponedTopicInfoCallbacks==null,"completion releases callbacks");
  cachedError.setTopicInfo(new TdApi.ForumTopicInfo());check(cachedError.calls==2,"rename does not replay initial callbacks");
  InfoHarness immediate=new InfoHarness();immediate.tdlib.topics.mode=1;immediate.withTopicInfo(immediate::ready);
  check(immediate.calls==1&&immediate.postponedTopicInfoCallbacks==null,"in-place callback delivered once");
  immediate.withTopicInfo(immediate::ready);check(immediate.calls==2&&immediate.tdlib.topics.registered==1,"known metadata reused");
  InfoHarness alreadyKnown=new InfoHarness();alreadyKnown.topicInfo=new TdApi.ForumTopicInfo();alreadyKnown.tdlib.topics.mode=1;
  alreadyKnown.withTopicInfo(alreadyKnown::ready);check(alreadyKnown.calls==1,"registering known topic does not duplicate callback");
  InfoHarness pending=new InfoHarness();pending.withTopicInfo(pending::ready);check(pending.calls==0,"network pending keeps fallback");
  pending.setTopicInfo(new TdApi.ForumTopicInfo());check(pending.calls==1,"async recovery");
  InfoHarness ordinary=new InfoHarness();ordinary.forumTopicKey=null;ordinary.withTopicInfo(ordinary::ready);
  check(ordinary.calls==0&&ordinary.tdlib.topics.registered==0,"ordinary messages excluded");
  System.out.println("topic metadata error and callback lifecycle checks passed");
 }
}
'''

class ForumInfoReadinessTests(unittest.TestCase):
    def run_info(self,negative=False):
        source=P.read_text();body=method(source,'protected final void withTopicInfo (')
        if negative:
            body=body.replace('tdlib.topics().findAndObserve(forumTopicKey, this);','TdlibForumTopicManager.Entry entry = tdlib.topics().findAndObserve(forumTopicKey, this); if (entry != null) { after.runWithBool(true); return; }')
        code=HARNESS.replace('\n WITH\n','\n'+body+'\n').replace('\n SET\n','\n'+method(source,'private void setTopicInfo (')+'\n').replace('\n GET\n','\n'+method(source,'protected final TdApi.ForumTopicInfo topicInfo (')+'\n')
        return run_java({'InfoHarness.java':code},'InfoHarness')

    def test_cached_error_and_recovery(self):
        r=self.run_info();self.assertEqual(r.returncode,0,r.stderr)
    def test_negative_cached_entry_means_ready(self):
        r=self.run_info(True);self.assertNotEqual(r.returncode,0);self.assertIn('NullPointerException',r.stderr)

if __name__=='__main__':unittest.main()
