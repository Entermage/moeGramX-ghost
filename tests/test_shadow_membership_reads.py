"""Real unread-completion/local-read methods; deterministic queues, not Android E2E.

Keep UI delivery separate from the TDLib local-read validator. A completed group
scan can otherwise mark newly unblocked messages as read after its cache clears.
"""
import unittest

from test_chat_navigation import block
from test_preview_filter import run_java
from test_shadow_membership import membership_sources, SHADOW

KEY = "moe/kirao/mgx/MoexShadowUnreadManager.java"


def read_sources():
    sources = membership_sources()
    methods = "\n".join(block(SHADOW, name) for name in (
        "private enum ScanOutcome",
        "private static void requestForChat (",
        "private static void request (@NonNull Tdlib",
        "private static void completeRequest (",
        "private static void markAllUnreadHiddenLocally (",
        "private static void readMessagesLocally (",
        "private static void finishLocalReadRequest (",
        "private static boolean isLocalReadRequestCurrent (",
        "private static boolean isCurrentLocked (",
    ))
    sources[KEY] = sources[KEY].replace(
        "private static class LocalReadRequest {}",
        block(SHADOW, "private static final class LocalReadRequest"),
    ).replace("__HARNESS__", r"""
  private static final long LOCAL_READ_DEDUP_DELAY_MS=2000,
    SCAN_INCOMPLETE_RETRY_DELAY_MS=1000, SCAN_REQUEST_GAP_MS=250;
  private static class Log {static void i(String f,java.lang.Object... args){}}
__READ_METHODS__
__HARNESS__
""".replace("__READ_METHODS__", methods))
    api = "org/drinkless/tdlib/TdApi.java"
    sources[api] = sources[api].replace(
        "public static class Object {}",
        "public static class Object {public int getConstructor(){return 0;}}",
    ).replace(
        "public static class Error extends Object {",
        "public static class Error extends Object { public static final int CONSTRUCTOR=9; public int getConstructor(){return CONSTRUCTOR;}",
    ).replace(
        'public String content="ordinary";',
        'public String content="ordinary"; public boolean isOutgoing; public Object sendingState;',
    ).replace("public class TdApi {", r"""
public class TdApi {
  public static class ChatType {public int getConstructor(){return 0;}}
  public static class ChatTypeBasicGroup extends ChatType {public static final int CONSTRUCTOR=10;public int getConstructor(){return CONSTRUCTOR;}}
  public static class ChatTypeSupergroup extends ChatType {public static final int CONSTRUCTOR=11;public int getConstructor(){return CONSTRUCTOR;}}
  public static class ChatTypeSecret extends ChatType {public static final int CONSTRUCTOR=12;public int getConstructor(){return CONSTRUCTOR;}}
  public static class Supergroup {public boolean isForum;}
  public static class Chat {
    public long id=-100,lastReadInboxMessageId=10,privateUserId;
    public int unreadCount=2,unreadMentionCount,unreadReactionCount;
    public boolean isMarkedAsUnread;
    public ChatType type=new ChatTypeBasicGroup();
    public Message lastMessage=new Message(42);
    public Chat(){lastMessage.id=12;lastMessage.chatId=id;}
  }
""")
    sources["org/thunderdog/challegram/data/TD.java"] = r"""
package org.thunderdog.challegram.data;
import org.drinkless.tdlib.TdApi;
public class TD {public static long getUserId(TdApi.Chat c){return c.privateUserId;}}
"""
    tdlib = "org/thunderdog/challegram/telegram/Tdlib.java"
    sources[tdlib] = sources[tdlib].replace("public class Tdlib {", r"""
public class Tdlib {
  public @interface GhostReadScope {int NONE=0,ALL=1;}
  public static int ghostReadScope(TdApi.Chat c){return GhostReadScope.ALL;}
  public TdApi.Chat currentChat;
  public int localReadSubmissions,localReadCommits;
  public final Queue<Runnable> localReads=new ArrayDeque<>();
  public boolean isChannelChat(TdApi.Chat c){return false;}
  public TdApi.Supergroup chatToSupergroup(long c){return new TdApi.Supergroup();}
  public TdApi.Chat chat(long c){return currentChat!=null&&currentChat.id==c?currentChat:null;}
  public boolean isChatReadSnapshotCurrent(long chat,int unread,long last,long top,int scope){
    TdApi.Chat c=chat(chat);
    return c!=null&&c.unreadCount==unread&&c.lastReadInboxMessageId==last&&c.lastMessage.id==top;
  }
  public void readMessagesLocally(int scope,long chat,long target,int unread,long last,
      java.util.function.BooleanSupplier current,java.util.function.Consumer<TdApi.Object> callback){
    localReadSubmissions++;
    localReads.add(()->{if(current.getAsBoolean()){localReadCommits++;callback.accept(new TdApi.Object());}
      else callback.accept(new TdApi.Error(400,"stale"));});
  }
  public void flushLocalReads(){while(!localReads.isEmpty())localReads.remove().run();}
""")
    return sources


HARNESS = r"""
  static int checks,successes,failures;
  static void check(boolean value,String reason){checks++;if(!value)throw new AssertionError(reason);}
  static Tdlib ready(int account){
    Tdlib t=new Tdlib(account);t.currentChat=new TdApi.Chat();
    ensureHiddenUsers(t,r->{});t.ui().flush();t.answer(42);t.ui().flush();return t;
  }
  static ChatRequest scanned(Tdlib t,int hidden){
    requestForChat(t,t.currentChat,(success,count)->{if(success)successes++;else failures++;},false);
    AccountState state=accountState(t);
    ChatRequest r=state.chatRequests.get(t.currentChat.id);
    check(r!=null&&!r.valid,"real group request queued before completing scan");
    completeRequest(t,state,r,ScanOutcome.SUCCESS,hidden);
    check(r.valid&&r.callbacks.isEmpty(),"completeRequest copied and posted callbacks");
    return r;
  }
  static void done(Tdlib t){t.ui().flush();t.flushLocalReads();t.ui().flush();}
  public static void main(String[] args){
    // The group has two inbox unread messages; unlike a private chat there is no
    // single-user predicate to repair a stale count at result delivery time.
    Tdlib t=ready(100);int before=failures;scanned(t,2);
    check(t.localReadSubmissions==0,"scan completion has not yet delivered its UI callback");
    onBlockListChanged(t,42,false);done(t);
    __PRIMARY_ASSERT__
    __MORE_CHECKS__
    System.out.println("Shadow local-read race: "+checks+" production checks passed");
  }
"""

MORE_CHECKS = r"""
    check(failures==before+1,"stale scan result reports unsuccessful instead of hiding unread count");
    check(areHiddenUsersReady(t)&&!isMainBlocked(t,42)&&t.sends==1,"unblock preserves authoritative membership without refetch");

    Tdlib valid=ready(101);scanned(valid,2);done(valid);
    check(valid.localReadSubmissions==1&&valid.localReadCommits==1,"unchanged all-hidden group still reads locally");

    Tdlib partial=ready(102);scanned(partial,1);done(partial);
    check(partial.localReadSubmissions==0,"partially hidden unread range stays unread");

    Tdlib marked=ready(103);marked.currentChat.isMarkedAsUnread=true;scanned(marked,2);done(marked);
    check(marked.localReadSubmissions==0,"explicit unread marker stays unread");

    Tdlib queued=ready(104);scanned(queued,2);queued.ui().flush();
    check(queued.localReadSubmissions==1&&queued.localReadCommits==0,"local-read validator remains pending after UI callback");
    onBlockListChanged(queued,42,false);done(queued);
    check(queued.localReadCommits==0,"unblock after submission invalidates pending local-read validator");

    Tdlib manual=ready(105);onBlockListChanged(manual,42,false);MoexConfig.instance().set(105,42);manual.ui().flush();
    scanned(manual,2);MoexConfig.instance().set(105);done(manual);
    check(manual.localReadSubmissions==0,"manual unban also rejects completed group scan");

    Tdlib logout=ready(106);scanned(logout,2);invalidate(logout);done(logout);
    check(logout.localReadSubmissions==0,"logout invalidates scan callback before local read");

    Tdlib snapshot=ready(107);scanned(snapshot,2);snapshot.ui().flush();snapshot.currentChat.unreadCount=3;done(snapshot);
    check(snapshot.localReadSubmissions==1&&snapshot.localReadCommits==0,"new inbox message invalidates TDLib snapshot validator");

    Tdlib a=ready(108),b=ready(109);scanned(a,2);scanned(b,2);onBlockListChanged(a,42,false);done(a);done(b);
    check(a.localReadCommits==0&&b.localReadCommits==1,"unblock invalidation remains isolated by account");

    Tdlib late=ready(110);scanned(late,2);onBlockListChanged(late,42,false);onBlockListChanged(late,42,true);done(late);
    check(late.localReadSubmissions==0,"unblock then reblock cannot revive an old scan result");
    scanned(late,2);done(late);
    check(late.localReadCommits==1,"a new scan after reblock still completes normally");
"""


class ShadowMembershipReadsTest(unittest.TestCase):
    def test_completed_group_scan_and_queued_local_read_are_invalidated(self):
        sources = read_sources()
        harness = HARNESS.replace("__PRIMARY_ASSERT__", r'''
    check(t.localReadSubmissions==0&&t.localReadCommits==0,"unblock before UI delivery must not locally read newly visible group messages");
''').replace("__MORE_CHECKS__", MORE_CHECKS)
        sources[KEY] = sources[KEY].replace("__HARNESS__", harness)
        run_java(sources, "moe.kirao.mgx.MoexShadowUnreadManager")

    def test_negative_control_reproduces_stale_read_without_generation_bump(self):
        sources = read_sources()
        original = block(SHADOW, "private static void clearUnreadRequests (")
        self.assertEqual(original.count("state.generation++;"), 1)
        sources[KEY] = sources[KEY].replace(original, original.replace("state.generation++;", ""))
        harness = HARNESS.replace("__PRIMARY_ASSERT__", r'''
    check(t.localReadSubmissions==1&&t.localReadCommits==1,"negative control must reproduce the original stale group local read");
''').replace("__MORE_CHECKS__", "")
        sources[KEY] = sources[KEY].replace("__HARNESS__", harness)
        run_java(sources, "moe.kirao.mgx.MoexShadowUnreadManager")


if __name__ == "__main__":
    unittest.main()
