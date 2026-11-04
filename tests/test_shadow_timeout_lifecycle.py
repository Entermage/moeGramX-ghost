"""Production Shadow lifecycle with deterministic time/network doubles.

All scheduler, membership, scan, timeout, completion and invalidation methods are
extracted unchanged from the production source. Only the Android clock/UI queue,
TDLib transport and configuration are doubles. This tests outstanding Java API
callbacks, not native MTProto query coalescing or Android/Telegram E2E behavior.
"""
import re
import unittest

from test_chat_navigation import block
from test_preview_filter import run_java
from test_shadow_membership import membership_sources, SHADOW

KEY = "moe/kirao/mgx/MoexShadowUnreadManager.java"


def lifecycle_sources():
    sources = membership_sources()
    source = SHADOW.read_text()
    methods = (
        "private enum ScanOutcome", "private interface ScanCallback",
        "private static void request (@NonNull Tdlib",
        "private static void enqueueScanRequest (", "private static void scheduleScanPump (",
        "private static void runScanPump (", "private static void executeRequest (",
        "private static void searchNextUser (", "private static void searchUserPage (",
        "private static void loadHistoryPage (", "private static long beginScanAttempt (",
        "private static boolean deferScanForCooldown (", "private static boolean finishScanAttempt (",
        "private static void onScanAttemptTimeout (", "private static void completeRequest (",
        "private static boolean isCurrent (AccountState accountState, ChatRequest",
        "private static boolean isCurrentLocked (", "private static void deliver (",
    )
    manager = sources[KEY].replace(
        "private static void scheduleScanPump(Tdlib t,AccountState s) {}", ""
    ).replace(
        "private static void enqueueScanRequest(Tdlib t,AccountState s,ChatRequest r) {}", ""
    ).replace(
        "private static void deliver(Tdlib t,Callback c,boolean success,int n) {t.ui().post(()->c.onResult(success,n));}", ""
    ).replace("import java.util.*;", "import java.util.*;\nimport tgx.td.Td;")
    constants = []
    for name in ("MAX_SCAN_REQUESTS", "SCAN_REQUEST_GAP_MS", "SCAN_INCOMPLETE_RETRY_DELAY_MS"):
        constants.append(re.search(r"private static final (?:int|long) " + name + r"\s*=\s*[^;]+;", source).group())
    manager = manager.replace("__HARNESS__", "\n".join(constants) + "\n" +
                              "\n".join(block(SHADOW, name) for name in methods) + "\n__HARNESS__")
    sources[KEY] = manager
    api = "org/drinkless/tdlib/TdApi.java"
    sources[api] = sources[api].replace("public class TdApi {", r"""
public class TdApi {
  public static class Messages {public Message[] messages;public Messages(Message... m){messages=m;}}
  public static class FoundChatMessages {public Message[] messages;public long nextFromMessageId;public FoundChatMessages(Message... m){messages=m;}}
  public static class GetChatHistory {public long chat,from;public GetChatHistory(long c,long f,int o,int l,boolean local){chat=c;from=f;}}
  public static class SearchChatMessages {public long chat,from;public SearchChatMessages(long c,java.lang.Object topic,String q,MessageSenderUser s,long f,int o,int l,java.lang.Object filter){chat=c;from=f;}}
""").replace('public String content="ordinary";', 'public String content="ordinary"; public boolean isOutgoing;')
    tdlib = "org/thunderdog/challegram/telegram/Tdlib.java"
    sources[tdlib] = sources[tdlib].replace("public class Tdlib {", r"""
public class Tdlib {
  public interface HistoryHandler {void result(TdApi.Messages m,TdApi.Error e);}
  public interface SearchHandler {void result(TdApi.FoundChatMessages m,TdApi.Error e);}
  public static class Scan {
    public final java.lang.Object query;public final HistoryHandler handler;
    Scan(java.lang.Object q,HistoryHandler h){query=q;handler=h;}
    public void answer(TdApi.Messages m,TdApi.Error e){handler.result(m,e);}
  }
  public final ArrayList<Scan> scans=new ArrayList<>();
  public final List<Long> sendTimes=new ArrayList<>();
  public int scanSends,peakScans;
  public void send(TdApi.GetChatHistory q,HistoryHandler h){
    sends++;scanSends++;sendTimes.add(SystemClock.now);scans.add(new Scan(q,h));peakScans=Math.max(peakScans,scans.size());
  }
  public void send(TdApi.SearchChatMessages q,SearchHandler h){
    sends++;scanSends++;sendTimes.add(SystemClock.now);
    scans.add(new Scan(q,(m,e)->h.result(m==null?null:new TdApi.FoundChatMessages(m.messages),e)));
    peakScans=Math.max(peakScans,scans.size());
  }
  public Scan takeScan(){return scans.remove(0);}
  public void answerScan(TdApi.Messages m,TdApi.Error e){takeScan().answer(m,e);dispatcher.flush();}
""").replace("public void advance(long d){SystemClock.now+=d;flush();}", r"""
    public void advance(long d){
      long end=SystemClock.now+d;int count=0;
      while(!tasks.isEmpty()&&tasks.peek().time<=end){
        if(++count>100000)throw new AssertionError("timer loop");
        SystemClock.now=Math.max(SystemClock.now,tasks.peek().time);flush();
      }
      SystemClock.now=end;flush();
    }
""")
    return sources


COMMON = r"""
  static int checks,successes,failures,membershipSuccesses,membershipFailures;
  static int nextAccount=1000;
  static final Callback callback=(ok,n)->{if(ok)successes++;else failures++;};
  static final HiddenUsersCallback membership=ok->{if(ok)membershipSuccesses++;else membershipFailures++;};
  static void check(boolean value,String reason){checks++;if(!value)throw new AssertionError(reason);}
  static Tdlib empty(){return new Tdlib(nextAccount++);}
  static Tdlib ready(){Tdlib t=empty();ensureHiddenUsers(t,membership);t.ui().flush();t.answer(42);t.ui().flush();return t;}
  static void ask(Tdlib t,long chat,int unread,long top){request(t,chat,unread,90,top,callback,false);t.ui().flush();}
  static void ask(Tdlib t,long chat){ask(t,chat,1,100);}
  static TdApi.Messages one(){TdApi.Message m=new TdApi.Message(42);m.id=100;return new TdApi.Messages(m);}
  static void success(Tdlib t){t.answerScan(one(),null);t.ui().advance(500);}
  static void error(Tdlib t,int code){t.answerScan(null,new TdApi.Error(code,"temporary failure"));}
  static void mainChecks(){__SCENARIO__}
  public static void main(String[] args){mainChecks();System.out.println("Shadow timeout lifecycle: "+checks+" production checks passed");}
"""


class ShadowTimeoutLifecycleTest(unittest.TestCase):
    def run_scenario(self, scenario, mutate=None):
        sources = lifecycle_sources()
        if mutate:
            sources[KEY] = mutate(sources[KEY])
        sources[KEY] = sources[KEY].replace("__HARNESS__", COMMON.replace("__SCENARIO__", scenario))
        run_java(sources, "moe.kirao.mgx.MoexShadowUnreadManager")

    def test_history_and_search_stay_bounded_with_ten_minutes_of_demand(self):
        self.run_scenario(r"""
    for(int unread:new int[]{1,200}){
      Tdlib t=ready();ask(t,-100,unread,100);int before=failures;
      for(int i=0;i<600;i++){t.ui().advance(1000);ask(t,-100,unread,100);}
      check(t.scanSends==1&&t.scans.size()==1,"unresolved API must retain its permit for ten minutes");
      check(failures>before,"timeout still releases user waiters");
      check(t.peakScans==1,"no overlap of retries, including real search path");
      check(failures-before==601,"every old and renewed demand receives a terminal unknown result");
      check(accountState(t).chatRequests.get(-100L).callbacks.isEmpty(),"draining does not accumulate waiter callbacks");
    }
""")

    def test_single_retry_waits_for_real_completion_and_ignores_late_payload(self):
        self.run_scenario(r"""
    for(boolean fail:new boolean[]{false,true}){
      Tdlib t=ready();ask(t,-101);int before=successes;
      t.ui().advance(45000);check(t.scanSends==1,"45s retry cannot overtake old API");
      if(fail)error(t,500);else t.answerScan(one(),null);
      t.ui().advance(15000);
      check(t.scanSends==2&&t.scans.size()==1,"real completion wakes exactly one retry");
      check(successes==before,"late old payload cannot publish stale count");
      ChatRequest active=accountState(t).chatRequests.get(-101L);
      success(t);check(active.valid&&t.scans.isEmpty(),"fresh retry success becomes valid");
      t.ui().advance(600000);check(t.scanSends==2,"settled request stays settled");
    }
""")

    def test_thirty_second_deadline_finishes_waiters_exactly_once(self):
        self.run_scenario(r"""
    for(int unread:new int[]{1,200}){
      Tdlib t=ready();int before=failures,ok=successes;ask(t,-102,unread,100);
      t.ui().advance(29999);check(failures==before,"waiter remains pending before deadline");
      t.ui().advance(1);check(failures==before+1&&successes==ok,"30s deadline fails current waiter once");
      t.ui().advance(600000);check(failures==before+1&&t.scanSends==1,"unresolved transport cannot keep notifying old waiter");
      t.answerScan(one(),null);t.ui().advance(15000);
      check(failures==before+1&&successes==ok,"late success only drains transport, not stale caller");
      ask(t,-102,unread,100);success(t);
      check(successes==ok+1,"new demand receives recovered success");
    }
    Tdlib m=empty();int before=membershipFailures;ensureHiddenUsers(m,membership);m.ui().flush();
    m.ui().advance(29999);check(membershipFailures==before,"membership waiter before deadline");
    m.ui().advance(1);check(membershipFailures==before+1,"membership waiter released at 30s");
    m.ui().advance(600000);check(membershipFailures==before+1&&m.pending.size()==1,"membership deadline does not repeat or duplicate RPC");
    m.answer(9999);m.ui().flush();m.ui().advance(15000);
    check(membershipFailures==before+1&&!isMainBlocked(m,9999),"late membership payload cannot notify old caller");
    ensureHiddenUsers(m,membership);m.ui().flush();m.answer(42);m.ui().flush();
    check(isMainBlocked(m,42),"new membership demand can recover");
""")

    def test_queued_chats_are_bounded_and_continue_after_recovery(self):
        self.run_scenario(r"""
    Tdlib t=ready();int before=failures;for(int i=0;i<20;i++)ask(t,-200-i);
    t.ui().advance(30000);check(failures==before+20,"transport timeout releases waiters for all queued chats");
    for(ChatRequest r:accountState(t).chatRequests.values())check(r.callbacks.isEmpty(),"queued callback lists are drained");
    t.ui().advance(570000);check(t.scanSends==1&&t.scans.size()==1,"20 queued chats retain only one live API");
    t.answerScan(one(),null);t.ui().advance(15000);
    check(t.scanSends==2&&t.scans.size()==1,"late completion resumes queued work");
    long chat=((TdApi.GetChatHistory)t.scans.get(0).query).chat;
    check(chat!=-200,"other queued chat can make progress");
    success(t);check(accountState(t).chatRequests.get(chat).valid,"next chat completes normally");
""")

    def test_negative_control_without_api_reservation_reproduces_overlap(self):
        def release_permit(source):
            original = block(SHADOW, "private static long beginScanAttempt (")
            self.assertEqual(original.count("accountState.activeApiAttemptId = attemptId;"), 1)
            source = source.replace(original, original.replace("accountState.activeApiAttemptId = attemptId;", "accountState.activeApiAttemptId = 0;"))
            timeout = block(SHADOW, "private static void onScanAttemptTimeout (")
            self.assertIn("accountState.activeApiAttemptId != attemptId || ", timeout)
            return source.replace(timeout, timeout.replace("accountState.activeApiAttemptId != attemptId || ", ""))
        # This intentionally removes real transport reservation, without replacing
        # the scheduling algorithm, to prove the regression detects overlapping work.
        self.run_scenario(r"""
    Tdlib t=ready();ask(t,-800);
    for(int i=0;i<600;i++){t.ui().advance(1000);ask(t,-800);}
    check(t.scanSends>1&&t.scans.size()>1,"negative control must reproduce unresolved API accumulation");
""", mutate=release_permit)

    def test_new_membership_waiters_do_not_accumulate_while_draining(self):
        self.run_scenario(r"""
    Tdlib t=empty();ensureHiddenUsers(t,membership);t.ui().flush();t.ui().advance(30000);
    int before=membershipFailures;
    for(int i=0;i<600;i++){
      final int capture=i;
      ensureHiddenUsers(t,ok->{if(capture>=0){if(ok)membershipSuccesses++;else membershipFailures++;}});
      t.ui().advance(1000);
      check(accountState(t).hiddenUsersCallbacks.isEmpty(),"draining cannot retain fresh membership callbacks");
    }
    check(membershipFailures==before+600&&t.sends==1,"all new membership demand receives unknown without another API");
    t.answer(9999);t.ui().flush();t.ui().advance(15000);
    check(t.pending.size()==1,"merged membership demand resumes when transport drains");
    t.answer(42);t.ui().flush();check(isMainBlocked(t,42),"merged demand can recover membership snapshot");
""")

    def test_late_rate_limit_applies_only_to_matching_transport_generation(self):
        self.run_scenario(r"""
    Tdlib t=ready();ask(t,-810);t.ui().advance(45000);
    t.answerScan(null,new TdApi.Error(429,"retry after 60"));t.ui().advance(59999);
    check(t.scanSends==1,"late 429 preserves its actual retry-after cooldown");
    t.ui().advance(1);check(t.scanSends==2,"matching transport resumes at cooldown boundary");success(t);
    Tdlib u=ready();ask(u,-811);Tdlib.Scan old=u.takeScan();
    u.auth=new TdApi.AuthorizationStateClosed();invalidate(u);u.auth=new TdApi.AuthorizationStateReady();
    ensureHiddenUsers(u,membership);u.ui().flush();long token=accountState(u).activeApiAttemptId;
    long cooldown=accountState(u).scanRetryAfterUptimeMillis;
    old.answer(null,new TdApi.Error(429,"retry after 600"));u.ui().flush();
    check(accountState(u).activeApiAttemptId==token,"old error cannot release new transport token");
    check(accountState(u).scanRetryAfterUptimeMillis==cooldown,"old error cannot delay new authorization");
    u.answer(42);u.ui().flush();ask(u,-812);u.ui().advance(500);success(u);
    check(accountState(u).chatRequests.get(-812L).valid,"new authorization succeeds after old rate-limit callback");
""")

    def test_snapshot_replacement_and_manual_invalidation_keep_transport_slot(self):
        self.run_scenario(r"""
    Tdlib t=ready();ask(t,-300);t.ui().advance(10000);ask(t,-300,1,101);
    ChatRequest replacement=accountState(t).chatRequests.get(-300L);
    t.ui().advance(90000);check(t.scanSends==1,"replacement snapshot waits for old transport");
    t.answerScan(one(),null);t.ui().advance(15000);
    check(t.scanSends==2&&accountState(t).activeScanRequest==replacement,"replacement resumes after late completion");
    success(t);check(replacement.valid,"replacement can finish");

    Tdlib manual=ready();ask(manual,-301);MoexConfig.instance().set(manual.id(),55);manual.ui().flush();ask(manual,-301);
    ChatRequest newGeneration=accountState(manual).chatRequests.get(-301L);
    manual.ui().advance(600000);check(manual.scanSends==1,"manual invalidation preserves unresolved API permit");
    manual.answerScan(one(),null);manual.ui().advance(15000);
    check(manual.scanSends==2&&accountState(manual).activeScanRequest==newGeneration,"new manual generation resumes safely");
    success(manual);check(newGeneration.valid,"new manual generation succeeds");
""")

    def test_accounts_remain_independent_when_switching_back(self):
        self.run_scenario(r"""
    Tdlib a=ready(),b=ready();ask(a,-400);ask(b,-401);
    a.ui().advance(45000);b.ui().flush();check(a.scanSends==1&&b.scanSends==1,"each account owns one live API");
    a.answerScan(one(),null);a.ui().advance(15000);success(a);
    check(accountState(a).chatRequests.get(-400L).valid&&b.scans.size()==1,"one account recovers independently");
    ask(b,-401);b.ui().advance(90000);check(b.scanSends==1,"switching back cannot duplicate old account request");
    b.answerScan(one(),null);b.ui().advance(15000);success(b);
    check(accountState(b).chatRequests.get(-401L).valid,"second account independently recovers");
""")

    def test_logging_out_waits_and_closed_client_is_a_safe_boundary(self):
        self.run_scenario(r"""
    Tdlib t=ready();ask(t,-500);t.auth=new TdApi.AuthorizationStateLoggingOut();invalidate(t);
    ensureHiddenUsers(t,membership);t.ui().flush();t.ui().advance(600000);
    check(t.sends==2&&t.pending.isEmpty(),"logging out cannot release a still-live scan API");
    Tdlib.Scan old=t.takeScan();t.auth=new TdApi.AuthorizationStateClosed();invalidate(t);
    t.auth=new TdApi.AuthorizationStateReady();ensureHiddenUsers(t,membership);t.ui().flush();t.ui().advance(15000);
    check(t.pending.size()==1,"confirmed Closed permits a new authorization generation");
    long token=accountState(t).activeApiAttemptId;
    old.answer(one(),null);t.ui().flush();
    check(accountState(t).activeApiAttemptId==token&&t.pending.size()==1,"old callback cannot release new generation membership token");
    t.answer(42);t.ui().flush();ask(t,-501);check(t.scans.size()==1,"new login can scan normally");
    success(t);check(accountState(t).chatRequests.get(-501L).valid,"new login success is retained");
""")

    def test_membership_timeout_and_scan_share_one_transport_slot(self):
        self.run_scenario(r"""
    Tdlib t=empty();ensureHiddenUsers(t,membership);t.ui().flush();ask(t,-600);
    int before=membershipFailures;t.ui().advance(600000);
    check(t.sends==1&&t.pending.size()==1&&t.scans.isEmpty(),"membership timeout blocks retries and scans behind same permit");
    check(membershipFailures>before,"membership timeout reports failure to waiter");
    t.answer(9999);t.ui().flush();t.ui().advance(15000);
    check(!isMainBlocked(t,9999)&&t.pending.size()==1,"late old membership payload ignored, one fresh retry begins");
    t.answer(42);t.ui().flush();t.ui().advance(500);
    check(areHiddenUsersReady(t)&&t.scans.size()==1,"fresh membership lets scan queue progress");
    success(t);check(accountState(t).chatRequests.get(-600L).valid,"scan result succeeds after membership recovery");
""")

    def test_membership_pagination_late_error_and_old_generation(self):
        self.run_scenario(r"""
    Tdlib t=empty();ensureHiddenUsers(t,membership);t.ui().flush();long[] page=new long[100];for(int i=0;i<100;i++)page[i]=1000+i;
    t.answer(page);t.ui().advance(250);check(t.pending.peek().f.offset==100,"real second membership page is pending");
    t.ui().advance(45000);check(t.sends==2&&t.pending.size()==1,"second page timeout cannot spawn overlapping page");
    t.fail(500);t.ui().flush();t.ui().advance(15000);
    check(t.sends==3&&t.pending.peek().f.offset==0,"late failed page resumes one fresh snapshot");
    t.answer(42);t.ui().flush();check(isMainBlocked(t,42)&&!isMainBlocked(t,1000),"partial old page never becomes authoritative");

    Tdlib u=empty();ensureHiddenUsers(u,membership);u.ui().flush();Tdlib.Request old=u.pending.remove();
    u.auth=new TdApi.AuthorizationStateClosed();invalidate(u);u.auth=new TdApi.AuthorizationStateReady();ensureHiddenUsers(u,membership);u.ui().flush();
    long token=accountState(u).activeApiAttemptId;old.h.result(new TdApi.MessageSenders(9999),null);u.ui().flush();
    check(accountState(u).activeApiAttemptId==token&&u.pending.size()==1,"old membership callback cannot clear new token");
    u.answer(43);u.ui().flush();check(isMainBlocked(u,43)&&!isMainBlocked(u,9999),"new membership stays authoritative");
""")

    def test_healthy_completion_error_and_pagination_still_work(self):
        self.run_scenario(r"""
    Tdlib t=ready();ask(t,-700);success(t);t.ui().advance(600000);check(t.scanSends==1,"healthy scan timeout is inert");
    Tdlib retry=ready();ask(retry,-701);error(retry,500);retry.ui().advance(15000);check(retry.scanSends==2,"real transient failure keeps bounded retry");
    success(retry);check(accountState(retry).chatRequests.get(-701L).valid,"transient recovery succeeds");
    Tdlib permanent=ready();ask(permanent,-702);error(permanent,400);permanent.ui().advance(600000);check(permanent.scanSends==1,"permanent error does not retry-loop");
    Tdlib pages=ready();ask(pages,-703,2,101);pages.answerScan(one(),null);pages.ui().advance(250);
    check(pages.scanSends==2&&pages.scans.size()==1,"next page waits for completed transport");
    TdApi.Message m=new TdApi.Message(42);m.id=99;pages.answerScan(new TdApi.Messages(m),null);pages.ui().advance(500);
    check(accountState(pages).chatRequests.get(-703L).valid&&pages.peakScans==1,"real history pagination completes without overlap");
""")


if __name__ == "__main__":
    unittest.main()
