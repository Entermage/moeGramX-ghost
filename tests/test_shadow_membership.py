"""Production blacklist methods + filter with deterministic TDLib/UI doubles (not Android E2E)."""
from pathlib import Path
import unittest
from test_chat_navigation import block
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java"
SHADOW = JAVA / "moe/kirao/mgx/MoexShadowUnreadManager.java"
LOADER = JAVA / "org/thunderdog/challegram/component/chat/MessagesLoader.java"


def membership_sources():
    methods = "\n".join(block(SHADOW, name) for name in (
        "public interface Callback", "public interface HiddenUsersCallback", "public interface HiddenUsersListener",
        "public static boolean isMainBlocked (", "public static boolean areHiddenUsersReady (",
        "public static long hiddenUsersRevision (", "public static void ensureHiddenUsers (",
        "public static void refreshHiddenUsers (", "public static long blockListGeneration (",
        "public static void onBlockListResult (", "private static void deliverHiddenUsers (", "public static void cancelHiddenUsers (",
        "public static void addHiddenUsersListener (", "public static void removeHiddenUsersListener (",
        "private static void notifyHiddenUsersChanged (", "public static void invalidateAccount (",
        "private static boolean syncManualUsers (", "private static void rebuildHiddenUsers (",
        "private static void clearUnreadRequests (", "public static void invalidate (@NonNull Tdlib",
        "public static void onBlockListChanged (", "private static AccountState accountState (",
        "private static void invalidate (AccountState", "private static boolean hasHiddenUsersDemand (",
        "private static void scheduleHiddenUsersLoad (", "private static void resumeAccountWork (",
        "private static boolean isHiddenUsersCurrent (", "private static void loadHiddenUsers (",
        "private static void loadBlockedUsersPage (", "private static boolean finishHiddenUsersPageAttempt (",
        "private static void onHiddenUsersPageTimeout (", "private static void completeHiddenUsersLoad (",
        "private static void failAccountWaiters (",
        "private static void applyScanErrorCooldown (", "private static boolean isTransientScanError (",
        "private static boolean isCurrent (AccountState accountState, long generation)",
        "private static final class AccountState", "private static final class ChatRequest",
    ))
    source = r"""
package moe.kirao.mgx;
import android.os.SystemClock;
import androidx.annotation.NonNull;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import java.util.*;
import java.util.regex.*;
public final class MoexShadowUnreadManager {
  private static final int PAGE_SIZE=100, MAX_BLOCKED_USERS_PAGES=40;
  private static final long HIDDEN_USERS_REFRESH_INTERVAL_MS=60000;
  private static final long SCAN_FAILURE_COOLDOWN_MS=15000, SCAN_REQUEST_TIMEOUT_MS=30000, SCAN_PAGE_GAP_MS=250;
  private static final Pattern RETRY_AFTER_PATTERN=Pattern.compile("retry after (\\d+)");
  private static final Object STATES_LOCK=new Object();
  private static final Map<Tdlib, AccountState> ACCOUNT_STATES=new WeakHashMap<>();
  private static class LocalReadRequest {}
  private static void scheduleScanPump(Tdlib t,AccountState s) {}
  private static void enqueueScanRequest(Tdlib t,AccountState s,ChatRequest r) {}
  private static void deliver(Tdlib t,Callback c,boolean success,int n) {t.ui().post(()->c.onResult(success,n));}
__METHODS__
__HARNESS__
}
""".replace("__METHODS__", methods)
    return {
        "moe/kirao/mgx/MoexShadowUnreadManager.java": source,
        "moe/kirao/mgx/MoexMessageFilter.java": (JAVA / "moe/kirao/mgx/MoexMessageFilter.java").read_text(),
        "androidx/annotation/NonNull.java": "package androidx.annotation; public @interface NonNull {}",
        "android/os/SystemClock.java": "package android.os; public class SystemClock { public static long now; public static long uptimeMillis(){return now;} }",
        "tgx/td/ChatId.java": "package tgx.td; public class ChatId { public static long fromUserId(long u){return u;} }",
        "tgx/td/Td.java": "package tgx.td; import org.drinkless.tdlib.TdApi; public class Td { public static long getSenderUserId(TdApi.Message m){return m.userId;} public static TdApi.FormattedText textOrCaption(String s){return new TdApi.FormattedText(s);} }",
        "org/drinkless/tdlib/TdApi.java": r"""
package org.drinkless.tdlib;
public class TdApi {
  public static class AuthorizationState {}
  public static class AuthorizationStateReady extends AuthorizationState {}
  public static class AuthorizationStateLoggingOut extends AuthorizationState {}
  public static class AuthorizationStateClosed extends AuthorizationState {}
  public static class Object {}
  public static class Ok extends Object {}
  public static class Error extends Object { public int code; public String message; public Error(int c,String m){code=c;message=m;} }
  public static class BlockList {}
  public static class BlockListMain extends BlockList {}
  public static class BlockListStories extends BlockList {}
  public static class GetBlockedMessageSenders { public int offset,limit; public GetBlockedMessageSenders(BlockListMain b,int o,int l){offset=o;limit=l;} }
  public static class MessageSender { public int getConstructor(){return 0;} }
  public static class MessageSenderUser extends MessageSender { public static final int CONSTRUCTOR=1; public long userId; public MessageSenderUser(long u){userId=u;} public int getConstructor(){return CONSTRUCTOR;} }
  public static class MessageSenders { public int totalCount; public MessageSender[] senders; public MessageSenders(long... ids){ totalCount=ids.length==100?10000:ids.length; senders=new MessageSender[ids.length];for(int i=0;i<ids.length;i++)senders[i]=new MessageSenderUser(ids[i]); } }
  public static class Message { public long userId,chatId=-100,id; public String content="ordinary"; public Message(long u){userId=u;} }
  public static class FormattedText { public String text; public FormattedText(String s){text=s;} }
}
""",
        "moe/kirao/mgx/MoexConfig.java": r"""
package moe.kirao.mgx;
import java.util.*;
public class MoexConfig {
  public static boolean filterEnabled,filterInChats=true,filterCaseInsensitive;
  public static final String KEY_FILTER_PATTERNS="patterns";
  private static final MoexConfig INSTANCE=new MoexConfig();
  public static MoexConfig instance(){return INSTANCE;}
  public final Map<Integer,long[]> manual=new HashMap<>();
  public Runnable afterSnapshot;
  public long[] getShadowBannedUsers(int a){long[] ids=manual.getOrDefault(a,new long[0]).clone();Runnable r=afterSnapshot;afterSnapshot=null;if(r!=null)r.run();return ids;}
  public boolean isShadowBanned(int a,long u){for(long id:manual.getOrDefault(a,new long[0]))if(id==u)return true;return false;}
  public void set(int a,long... ids){manual.put(a,ids);MoexShadowUnreadManager.invalidateAccount(a);}
  public String getString(String k,String d){return d;}
}
""",
        "org/thunderdog/challegram/telegram/Tdlib.java": r"""
package org.thunderdog.challegram.telegram;
import java.util.*;
import org.drinkless.tdlib.TdApi;
import android.os.SystemClock;
public class Tdlib {
  public TdApi.AuthorizationState auth=new TdApi.AuthorizationStateReady();
  public TdApi.AuthorizationState authorizationState(){return auth;}
  public final int account; public final Dispatcher dispatcher=new Dispatcher();
  public int sends; public Set<Long> cachedBlocked=new HashSet<>(); public Queue<Request> pending=new ArrayDeque<>();
  public Tdlib(int a){account=a;}
  public int id(){return account;} public boolean isSelfUserId(long u){return u==999;}
  public boolean chatFullyBlocked(long c){return cachedBlocked.contains(c);}
  public Dispatcher ui(){return dispatcher;}
  public interface Handler {void result(TdApi.MessageSenders s,TdApi.Error e);}
  public static class Request {public TdApi.GetBlockedMessageSenders f; public Handler h; Request(TdApi.GetBlockedMessageSenders f,Handler h){this.f=f;this.h=h;} }
  public void send(TdApi.GetBlockedMessageSenders f,Handler h){sends++;pending.add(new Request(f,h));}
  public void answer(long... ids){pending.remove().h.result(new TdApi.MessageSenders(ids),null);}
  public void answerPage(int total,long... ids){TdApi.MessageSenders page=new TdApi.MessageSenders(ids);page.totalCount=total;pending.remove().h.result(page,null);}
  public void fail(int code){pending.remove().h.result(null,new TdApi.Error(code,"failure"));}
  public static class Dispatcher {
    static class Task {long time,order;Runnable r;Task(long t,long o,Runnable r){time=t;order=o;this.r=r;}}
    long order;PriorityQueue<Task> tasks=new PriorityQueue<>(Comparator.<Task>comparingLong(t->t.time).thenComparingLong(t->t.order));
    public void post(Runnable r){postDelayed(r,0);}
    public void postDelayed(Runnable r,long d){tasks.add(new Task(SystemClock.now+d,order++,r));}
    public void flush(){int count=0;while(!tasks.isEmpty()&&tasks.peek().time<=SystemClock.now){if(++count>1000)throw new AssertionError("UI loop");tasks.remove().r.run();}}
    public void advance(long d){SystemClock.now+=d;flush();}
  }
}
""",
    }


class ShadowMembershipTest(unittest.TestCase):
    def test_production_membership_lifecycle(self):
        sources=membership_sources()
        harness=r"""
  static int checks;
  static void check(boolean v,String why){checks++;if(!v)throw new AssertionError(why);}
  static int success,failures,changes;
  static HiddenUsersCallback cb=ready->{if(ready)success++;else failures++;};
  public static void main(String[] args){
    Tdlib a=new Tdlib(7),b=new Tdlib(8);
    addHiddenUsersListener(a,r->changes++);
    ensureHiddenUsers(a,cb);ensureHiddenUsers(a,ready->{});a.ui().flush();
    check(a.sends==1&&!areHiddenUsersReady(a)&&success==0,"initial membership is gated and coalesced");
    a.answer(42,43);a.ui().flush();
    check(areHiddenUsersReady(a)&&success==1&&changes==1,"one readiness notification and completion");
    check(a.cachedBlocked.isEmpty()&&MoexMessageFilter.shouldHideInChat(a,new TdApi.Message(42),false),"server blocked user hidden without private chat cache");
    check(!MoexMessageFilter.shouldHideInChat(a,new TdApi.Message(44),false),"ordinary sender remains visible");
    check(!MoexMessageFilter.isShadowBannedUser(b,42),"other account isolated");
    int sends=a.sends;ensureHiddenUsers(a,cb);cancelHiddenUsers(a,cb);a.ui().flush();
    check(success==1&&a.sends==sends,"ready fast-path cancellation is effective and does not reload");
    MoexConfig.instance().set(7,42,55);a.ui().flush();
    check(a.sends==sends&&areHiddenUsersReady(a),"manual edit retains ready server snapshot without refetch");
    long unreadGeneration=accountState(a).generation;
    onBlockListChanged(a,42,false);a.ui().flush();
    check(MoexMessageFilter.isShadowBannedUser(a,42),"manual ban survives server unblock");
    check(!isCurrent(accountState(a),unreadGeneration),"unblock invalidates queued unread results");
    MoexConfig.instance().set(7,55);a.ui().flush();
    a.cachedBlocked.add(42L);
    check(!MoexMessageFilter.isShadowBannedUser(a,42),"authoritative unblock wins over stale private chat");
    check(MoexMessageFilter.isShadowBannedUser(a,43)&&MoexMessageFilter.isShadowBannedUser(a,55),"server and manual sources stay separate");
    MoexConfig.instance().afterSnapshot=()->MoexConfig.instance().set(7,56);
    syncManualUsers(a,accountState(a),false);
    check(accountState(a).manualUserIds.equals(new HashSet<>(Arrays.asList(56L))),"newer manual sync wins over older captured snapshot");
    long oldReadGeneration=accountState(a).generation, oldRevision=hiddenUsersRevision(a);
    MoexConfig.instance().manual.put(7,new long[]{57});
    check(syncManualUsers(a,accountState(a),true)&&!isCurrent(accountState(a),oldReadGeneration)&&hiddenUsersRevision(a)>oldRevision&&accountState(a).hiddenUserIds.contains(57L),"manual snapshot and both read/render invalidations publish atomically");
    long publishedRevision=hiddenUsersRevision(a);notifyHiddenUsersChanged(a,accountState(a));
    check(hiddenUsersRevision(a)==publishedRevision,"notification does not delay or independently mutate render revision");
    int before=success;
    ensureHiddenUsers(a,cb);invalidate(a);a.ui().flush();
    check(success==before&&failures==1&&!areHiddenUsersReady(a)&&accountState(a).mainUserIds.isEmpty(),"logout cancels queued successful delivery and clears snapshot");
    ensureHiddenUsers(a,cb);a.ui().flush();a.answer(77);cancelHiddenUsers(a,cb);a.ui().flush();
    check(success==before&&isMainBlocked(a,77),"cancel after completion before UI delivery suppresses callback");
    check(!MoexConfig.instance().isShadowBanned(7,77),"server members never persisted into manual list");
    Tdlib c=new Tdlib(9);ensureHiddenUsers(c,cb);c.ui().flush();
    onBlockListChanged(c,88,true);onBlockListChanged(c,89,false);c.answer(89);c.ui().flush();
    check(isMainBlocked(c,88)&&!isMainBlocked(c,89),"mid-load block/unblock overrides win over snapshot");
    Tdlib d=new Tdlib(10);int initialFailures=failures;ensureHiddenUsers(d,cb);d.ui().flush();d.fail(500);d.ui().flush();
    check(d.sends==1&&failures==initialFailures&&!areHiddenUsersReady(d),"transient failure remains gated during cooldown");
    d.ui().advance(15000);check(d.sends==2,"one bounded automatic retry");d.fail(500);d.ui().flush();
    check(failures==initialFailures+1&&!areHiddenUsersReady(d),"exhausted retry reports failure, not empty success");
    d.ui().advance(60000);check(d.sends==2,"no retry loop after terminal failure");
    ensureHiddenUsers(d,cb);d.ui().flush();d.answer(90);d.ui().flush();check(isMainBlocked(d,90),"explicit retry recovers after error");
    Tdlib e=new Tdlib(11);ensureHiddenUsers(e,cb);e.ui().flush();e.fail(400);e.ui().flush();e.ui().advance(60000);
    check(e.sends==1&&!areHiddenUsersReady(e),"permanent failure does not loop");
    Tdlib f=new Tdlib(12);ensureHiddenUsers(f,cb);f.ui().flush();f.ui().advance(30000);f.ui().advance(15000);
    check(f.sends==1,"timeout retains the underlying API permit");
    f.pending.remove().h.result(new TdApi.MessageSenders(9999),null);f.ui().flush();
    check(f.sends==2,"real late completion permits one fresh retry");f.answer(91);f.ui().flush();
    check(!isMainBlocked(f,9999)&&isMainBlocked(f,91),"late timed-out result cannot replace newer snapshot");
    Tdlib g=new Tdlib(13);ensureHiddenUsers(g,cb);g.ui().flush();long[] page=new long[100];for(int i=0;i<100;i++)page[i]=1000+i;g.answer(page);g.ui().advance(250);
    check(!areHiddenUsersReady(g)&&g.pending.peek().f.offset==100,"multi-page membership not ready until complete");
    g.answer(2000);g.ui().flush();check(isMainBlocked(g,1000)&&isMainBlocked(g,2000),"complete multi-page union");
    int changeCount=changes;onBlockListChanged(a,77,true);a.ui().flush();check(changes==changeCount,"duplicate membership update causes no refresh");
    System.out.println("Shadow membership: "+checks+" production checks passed");
  }
"""
        key="moe/kirao/mgx/MoexShadowUnreadManager.java"
        sources[key]=sources[key].replace("__HARNESS__",harness)
        run_java(sources,"moe.kirao.mgx.MoexShadowUnreadManager")


    def test_production_history_gate_and_refresh(self):
        sources=membership_sources()
        key="moe/kirao/mgx/MoexShadowUnreadManager.java"
        sources[key]=sources[key].replace("__HARNESS__", "")
        methods="\n".join(block(LOADER,n) for n in (
            "public boolean isWaitingForHiddenUsers (", "public void retryHiddenUsersOnFocus (",
            "private boolean awaitHiddenUsers (",
        ))
        manager=JAVA / "org/thunderdog/challegram/component/chat/MessagesManager.java"
        refresh=block(manager,"public void refreshMessageFilter ()")
        sources["HistoryGateHarness.java"]=r"""
import java.util.*;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import moe.kirao.mgx.*;
public class HistoryGateHarness {
  static class MessageId { long chat,id;MessageId(long c,long i){chat=c;id=i;} }
  static class R {static class string {static final int Error=1;} }
  static class Toast {static final int LENGTH_SHORT=0;}
  static class UI {static int errors;static void showToast(int r,int t){errors++;}}
  static class Manager {int failures;Manager controller(){return this;}void setHistoryLoadingError(){}void onNetworkRequestSent(){failures++;}}
  static class Gate {
    boolean supportsHistoryPreview(){return true;}
    final Tdlib tdlib;final Manager manager=new Manager();
    long contextId; boolean isLoading; int loads;
    MoexShadowUnreadManager.HiddenUsersCallback hiddenUsersCallback;
    Runnable retryHiddenUsersLoad;
    Gate(Tdlib t){tdlib=t;}
    void load(MessageId id,int offset,int limit,int mode,boolean local,boolean top,boolean bottom){
      if(isLoading)return;
      if(!awaitHiddenUsers(id,offset,limit,mode,local,top,bottom))loads++;
    }
    // Production reuse() performs these cancellation steps before replacing its chat context.
    void reuse(){if(hiddenUsersCallback!=null)MoexShadowUnreadManager.cancelHiddenUsers(tdlib,hiddenUsersCallback);hiddenUsersCallback=null;retryHiddenUsersLoad=null;contextId++;isLoading=false;}
    __GATE__
  }
  static class TGMessage {long id,user;TGMessage(long id,long u){this.id=id;user=u;}TdApi.Message getMessage(){return new TdApi.Message(user);}long getChatId(){return -100;}long getId(){return id;}}
  static class Adapter {List<TGMessage> items=new ArrayList<>();int removed;int getMessageCount(){return items.size();}TGMessage getMessage(int i){return i<0||i>=items.size()?null:items.get(i);}void removeItem(int i){items.remove(i);removed++;}}
  static class Layout {int findFirstVisibleItemPosition(){return 0;}}
  static class Reload {
    long chat=-100;boolean waiting;int loads;MessageId anchor;
    long getChatId(){return chat;}boolean isWaitingForHiddenUsers(){return waiting;}
    void loadFromMessage(MessageId id,int m,boolean force){if(force)throw new AssertionError("cleared ordinary messages");anchor=id;loads++;}
    void loadFromStart(MessageId id){anchor=id;loads++;}
  }
  static class Refresh {
    final Tdlib tdlib;final Reload loader=new Reload();final Adapter adapter=new Adapter();final Layout manager=new Layout();
    static final int HIGHLIGHT_MODE_POSITION_RESTORE=3;
    Refresh(Tdlib t){tdlib=t;}
    __REFRESH__
  }
  static int checks;static void check(boolean b,String m){checks++;if(!b)throw new AssertionError(m);}
  public static void main(String[] args){
    Tdlib a=new Tdlib(30);Gate gate=new Gate(a);MessageId id=new MessageId(-100,0);
    gate.load(id,0,20,0,true,true,true);gate.load(id,0,20,0,true,true,true);a.ui().flush();
    check(gate.loads==0&&gate.isWaitingForHiddenUsers()&&a.sends==1,"unknown blacklist cannot start or duplicate first history");
    int[] extraRefresh={0};MoexShadowUnreadManager.addHiddenUsersListener(a,r->{if(!gate.isWaitingForHiddenUsers())extraRefresh[0]++;});
    a.answer(42);a.ui().flush();
    check(gate.loads==1&&!gate.isWaitingForHiddenUsers()&&extraRefresh[0]==0,"ready resumes gate once without listener reload loop");
    Tdlib b=new Tdlib(31);Gate cancelled=new Gate(b);cancelled.load(id,0,20,0,true,true,true);b.ui().flush();cancelled.reuse();b.answer(42);b.ui().flush();
    check(cancelled.loads==0,"cancelled/switched chat cannot resume old history");
    Tdlib c=new Tdlib(32);Gate failed=new Gate(c);failed.load(id,0,20,0,true,true,true);c.ui().flush();c.fail(400);c.ui().flush();
    check(failed.loads==0&&!failed.isLoading&&failed.manager.failures==1&&UI.errors==1,"load failure releases spinner but never treats unknown membership as visible history");
    c.ui().advance(15000);failed.retryHiddenUsersOnFocus();c.ui().flush();c.answer(43);c.ui().flush();
    check(failed.loads==1&&c.sends==2,"next focus retries failed initial gate");
    failed.retryHiddenUsersOnFocus();check(failed.loads==1,"focus after recovery cannot repeatedly reload");
    Refresh refresh=new Refresh(a);TGMessage ordinary=new TGMessage(1,44);refresh.adapter.items.add(ordinary);refresh.adapter.items.add(new TGMessage(2,42));
    refresh.refreshMessageFilter();
    check(refresh.adapter.items.size()==1&&refresh.adapter.items.get(0)==ordinary&&refresh.loader.anchor.id==1,"refresh immediately removes hidden item and preserves ordinary page and anchor");
    refresh.loader.waiting=true;refresh.refreshMessageFilter();check(refresh.loader.loads==1,"readiness listener does not restart an already-waiting history");
    System.out.println("History membership gate: "+checks+" production checks passed");
  }
}
""".replace("__GATE__",methods).replace("__REFRESH__",refresh)
        tdkey="org/thunderdog/challegram/telegram/Tdlib.java"
        sources[tdkey]=sources[tdkey].replace("public int id(){return account;}","public boolean isChannel(long c){return false;} public int id(){return account;}")
        run_java(sources,"HistoryGateHarness")

if __name__=="__main__": unittest.main()

