"""Extract production search methods and exercise delayed UI delivery deterministically."""
import unittest
from test_forum_requests import STUBS, SOURCE
from test_forum_navigation_counters import run_java
from test_forum_scope import method

HARNESS=r'''
package moe.kirao.mgx.topics;
import java.util.*;import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;
class Parent {protected void onSearchInputChanged(String q){} protected void onLeaveSearchMode(){}}
public class SearchHarness extends Parent {
 final Tdlib tdlib=new Tdlib();final Chat chat=new Chat();static class Chat{long id=-100;}
 boolean focused=true,searchMode=true,destroyed;String searchQuery="";long searchGeneration;Runnable pendingSearch;
 static final long SEARCH_DELAY_MS=350;List<TdApi.ForumTopic> results;int published;
 boolean isDestroyed(){return destroyed;}boolean isFocused(){return focused;}boolean inSearchMode(){return searchMode;}
 void runOnUiThreadOptional(Runnable r){tdlib.ui().post(r);}void setSearchResults(List<TdApi.ForumTopic> r){results=r;published++;}
 METHODS
 static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
 static TdApi.ForumTopics page(String name){TdApi.ForumTopic t=new TdApi.ForumTopic();t.info=new TdApi.ForumTopicInfo(-100,1,name);return new TdApi.ForumTopics(1,new TdApi.ForumTopic[]{t},0,0,0);}
 public static void main(String[] args){
  SearchHarness s=new SearchHarness();s.onSearchInputChanged(" A ");s.tdlib.clock.advance(349);check(ForumRequests.calls.isEmpty(),"typing debounce");s.tdlib.clock.advance(1);check(ForumRequests.calls.size()==1,"debounced query sent");
  // The old callback has already been posted to the UI, so cancel alone cannot retract it.
  ForumRequests.calls.get(0).onResult(page("old A"),null);s.onSearchInputChanged("B");s.onSearchInputChanged("A");s.tdlib.clock.advance(0);
  check(s.results==null,"A-B-A rejects already queued old A result");s.tdlib.clock.advance(350);check(ForumRequests.calls.size()==2,"latest A sent once");
  ForumRequests.calls.get(1).onResult(page("new A"),null);s.tdlib.clock.advance(0);check(s.results.get(0).info.name.equals("new A"),"current result published");
  s.focused=false;s.cancelSearchRequests();s.onSearchInputChanged("paused");s.tdlib.clock.advance(350);check(ForumRequests.calls.size()==2,"paused page cannot request");
  s.focused=true;s.resumeSearch();s.resumeSearch();s.tdlib.clock.advance(0);check(ForumRequests.calls.size()==3,"focus resumes pending query once");
  ForumRequests.calls.get(2).onResult(page("late paused"),null);s.focused=false;s.cancelSearchRequests();s.tdlib.clock.advance(0);check(s.results.get(0).info.name.equals("new A"),"blur rejects queued callback");
  s.focused=true;s.resumeSearch();s.tdlib.clock.advance(0);check(ForumRequests.calls.size()==4,"second resume fetches current query");
  s.searchMode=false;s.onLeaveSearchMode();ForumRequests.calls.get(3).onResult(page("closed"),null);s.tdlib.clock.advance(0);s.resumeSearch();s.tdlib.clock.advance(1000);check(s.results==null&&ForumRequests.calls.size()==4,"closed search cannot resurrect");
 }
}'''

class ForumSearchLifecycleTests(unittest.TestCase):
    def run_harness(self,negative=None):
        source=(SOURCE.parent/'ForumTopicsController.java').read_text()
        methods='\n'.join(method(source,s) for s in ['protected void onSearchInputChanged (','private void scheduleSearch (','private void cancelPendingSearch (','private void cancelSearchRequests (','private void resumeSearch (','private void searchTopics (','protected void onLeaveSearchMode ('])
        if negative=='generation':methods=methods.replace('generation != searchGeneration || ','')
        if negative=='resume':methods=methods.replace('scheduleSearch(searchQuery, 0);','')
        f=dict(STUBS);f.pop('moe/kirao/mgx/topics/QueueHarness.java')
        f['moe/kirao/mgx/topics/ForumRequests.java']='''package moe.kirao.mgx.topics;
import java.util.*;import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;
public class ForumRequests {static List<Tdlib.ResultHandler<TdApi.ForumTopics>> calls=new ArrayList<>();
public static void send(Tdlib t,Object owner,TdApi.GetForumTopics q,Tdlib.ResultHandler<TdApi.ForumTopics> h){calls.add(h);}public static void cancel(Tdlib t,Object owner){} }'''
        f['moe/kirao/mgx/topics/XgramForums.java']='''package moe.kirao.mgx.topics;import org.drinkless.tdlib.TdApi;import org.thunderdog.challegram.telegram.Tdlib;
public class XgramForums {static TdApi.ForumTopic normalizeUnread(Tdlib t,TdApi.ForumTopic v){return v;} }'''
        f['moe/kirao/mgx/topics/SearchHarness.java']=HARNESS.replace('METHODS',methods)
        return run_java(f,'moe.kirao.mgx.topics.SearchHarness')
    def test_search_debounce_pause_resume_and_generation(self):
        r=self.run_harness();self.assertEqual(r.returncode,0,r.stderr)
    def test_negative_same_query_callback(self):
        r=self.run_harness('generation');self.assertNotEqual(r.returncode,0);self.assertIn('old A result',r.stderr)
    def test_negative_missing_resume(self):
        r=self.run_harness('resume');self.assertNotEqual(r.returncode,0);self.assertIn('focus resumes',r.stderr)
    def test_lifecycle_hooks(self):
        s=(SOURCE.parent/'ForumTopicsController.java').read_text()
        for signature in ['public void onFocus (','public void onActivityResume (']:
            self.assertIn('resumeSearch();',method(s,signature))
        self.assertIn('cancelSearchRequests();',method(s,'private void releaseList ('))

    def test_search_results_receive_live_updates(self):
        s=(SOURCE.parent/'ForumTopicsController.java').read_text()
        update=method(s,'private void updateSearchTopic (')
        f=dict(STUBS);f.pop('moe/kirao/mgx/topics/QueueHarness.java')
        f['androidx/annotation/Nullable.java']='package androidx.annotation;public @interface Nullable {}'
        f['moe/kirao/mgx/topics/ForumTopicSnapshotUpdates.java']=(SOURCE.parent/'ForumTopicSnapshotUpdates.java').read_text()
        f['moe/kirao/mgx/topics/LiveSearchHarness.java']=r'''
package moe.kirao.mgx.topics;
import java.util.*;import org.drinkless.tdlib.TdApi;
public class LiveSearchHarness {
 static class Chat {long id=-100;}Chat chat=new Chat();boolean focused=true,mode=true;
 boolean isFocused(){return focused;}boolean inSearchMode(){return mode;}boolean isDestroyed(){return false;}
 static class TGForumTopic {TdApi.ForumTopic value;void setTopic(TdApi.ForumTopic v){value=v;}}
 Map<Integer,TGForumTopic> rows=new HashMap<>();List<TdApi.ForumTopic> searchResults=new ArrayList<>();
 static class Adapter {int calls;void notifyItemChanged(int i){calls++;}}Adapter adapter=new Adapter();
 UPDATE
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args){
  LiveSearchHarness s=new LiveSearchHarness();TdApi.ForumTopic t=new TdApi.ForumTopic();t.info=new TdApi.ForumTopicInfo(-100,7,"old");t.lastMessage=new TdApi.Message(100);t.unreadCount=4;
  s.searchResults.add(t);s.rows.put(7,new TGForumTopic());
  s.updateSearchTopic(-100,7,new TdApi.ForumTopicInfo(-100,7,"new"),null);
  check(s.searchResults.get(0).info.name.equals("new")&&s.rows.get(7).value==s.searchResults.get(0),"search row and binding receive new info");
  TdApi.UpdateForumTopic u=new TdApi.UpdateForumTopic();u.chatId=-100;u.forumTopicId=7;u.lastReadInboxMessageId=100;u.unreadMentionCount=8;
  s.updateSearchTopic(-100,7,null,u);check(s.searchResults.get(0).unreadCount==0&&s.searchResults.get(0).unreadMentionCount==8,"search counters update");
  s.updateSearchTopic(-101,7,new TdApi.ForumTopicInfo(-101,7,"wrong"),null);s.updateSearchTopic(-100,8,new TdApi.ForumTopicInfo(-100,8,"missing"),null);
  s.focused=false;s.updateSearchTopic(-100,7,new TdApi.ForumTopicInfo(-100,7,"blurred"),null);
  check(s.adapter.calls==2&&s.searchResults.get(0).info.name.equals("new"),"wrong chat and blurred callbacks ignored");
 }
}'''.replace('UPDATE',update)
        r=run_java(f,'moe.kirao.mgx.topics.LiveSearchHarness');self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('updateSearchTopic(info.chatId, info.forumTopicId, info, null)',s)
        self.assertIn('updateSearchTopic(update.chatId, update.forumTopicId, null, update)',s)

if __name__=='__main__':unittest.main()
