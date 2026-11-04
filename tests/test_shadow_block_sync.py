"""Production blacklist synchronization with deterministic transport/clock doubles."""
import unittest

from test_chat_navigation import block
from test_preview_filter import run_java
from test_shadow_membership import membership_sources, JAVA
from test_shadow_timeout_lifecycle import lifecycle_sources, COMMON

KEY = "moe/kirao/mgx/MoexShadowUnreadManager.java"
TDLIB = "org/thunderdog/challegram/telegram/Tdlib.java"
API = "org/drinkless/tdlib/TdApi.java"


def run_case(body, *, sources=None):
    sources = lifecycle_sources() if sources is None else sources
    sources[KEY] = sources[KEY].replace("__HARNESS__", COMMON.replace("__SCENARIO__", body).replace("Shadow timeout lifecycle:", "Blacklist sync:"))
    run_java(sources, "moe.kirao.mgx.MoexShadowUnreadManager")


def event_sources(old_local=False, old_profile=False):
    sources = lifecycle_sources()
    local = block(JAVA / TDLIB, "public void blockSender (").replace("@Nullable ", "")
    if old_local:
        local = "public void blockSender(TdApi.MessageSender sender,TdApi.BlockList blockList,Client.ResultHandler handler){client().send(new TdApi.SetMessageSenderBlockList(sender,blockList),handler);}"
    sources[TDLIB] = sources[TDLIB].replace("public class Tdlib {", """
import org.drinkless.tdlib.Client;
import moe.kirao.mgx.MoexShadowUnreadManager;
public class Tdlib {
  public final Client localClient=new Client();
  public Client client(){return localClient;}
  public void uiExecute(Runnable r){ui().post(r);}
""" + local)
    sources["org/drinkless/tdlib/Client.java"] = """
package org.drinkless.tdlib;
public class Client {
  public interface ResultHandler {void onResult(TdApi.Object result);}
  public java.util.Queue<ResultHandler> pending=new java.util.ArrayDeque<>();
  public void send(TdApi.SetMessageSenderBlockList f,ResultHandler h){pending.add(h);}
  public void answer(TdApi.Object result){pending.remove().onResult(result);}
}
"""
    sources[API] = sources[API].replace("public class TdApi {", """
public class TdApi {
  public static class SetMessageSenderBlockList {public SetMessageSenderBlockList(MessageSender s,BlockList b){}}
  public static class UserFullInfo {public BlockList blockList; public String bio;}
  public static class UpdateUserFullInfo {public long userId; public UserFullInfo userFullInfo=new UserFullInfo();}
""")
    profile = block(JAVA / "org/thunderdog/challegram/telegram/TdlibCache.java", "void onUpdateUserFull (")
    if old_profile:
        profile = profile.replace("    MoexShadowUnreadManager.onBlockListChanged(tdlib, update.userId,\n      update.userFullInfo.blockList instanceof TdApi.BlockListMain);\n", "")
    sources[KEY] = sources[KEY].replace("__HARNESS__", """
  static class UserCache {
    final Tdlib tdlib; final Object dataLock=new Object(); long myUserId;
    final List<Object> myUserListeners=new ArrayList<>();
    UserCache(Tdlib t){tdlib=t;}
    boolean putUserFull(long u,TdApi.UserFullInfo f){return true;}
    void notifyUserFullListeners(long u,TdApi.UserFullInfo f){}
    void notifyMyUserBioListeners(Iterator<Object> i,String b){}
""" + profile + "\n}\n__HARNESS__")
    return sources


class ShadowBlockSyncTest(unittest.TestCase):
    def test_local_success_and_profile_updates_without_private_chat(self):
        run_case(r"""
    Tdlib t=ready(); int[] callbacks={0}; long before=hiddenUsersRevision(t);
    t.blockSender(new TdApi.MessageSenderUser(55),new TdApi.BlockListMain(),r->callbacks[0]++);
    check(!isMainBlocked(t,55),"pending request cannot optimistically hide a sender");
    t.localClient.answer(new TdApi.Ok());t.ui().flush();
    check(isMainBlocked(t,55)&&t.cachedBlocked.isEmpty()&&callbacks[0]==1,"successful block hides without a private Chat or chat update");
    check(hiddenUsersRevision(t)>before,"successful block refreshes visible messages");
    t.blockSender(new TdApi.MessageSenderUser(56),new TdApi.BlockListMain(),r->callbacks[0]++);
    t.localClient.answer(new TdApi.Error(400,"denied"));
    check(!isMainBlocked(t,56)&&callbacks[0]==2,"failed block preserves filtering and caller error callback");
    t.blockSender(new TdApi.MessageSenderUser(55),null,r->{});t.localClient.answer(new TdApi.Ok());
    check(!isMainBlocked(t,55),"unblock immediately removes server membership");
    MoexConfig.instance().set(t.id(),42);
    t.blockSender(new TdApi.MessageSenderUser(42),null,r->{});t.localClient.answer(new TdApi.Ok());
    check(!isMainBlocked(t,42)&&MoexMessageFilter.isShadowBannedUser(t,42),"server unblock preserves separate manual ban");
    UserCache cache=new UserCache(t);TdApi.UpdateUserFullInfo update=new TdApi.UpdateUserFullInfo();
    update.userId=77;update.userFullInfo.blockList=new TdApi.BlockListMain();cache.onUpdateUserFull(update);
    check(isMainBlocked(t,77),"profile-only block event reaches filter with no Chat");
    long revision=hiddenUsersRevision(t);cache.onUpdateUserFull(update);
    check(hiddenUsersRevision(t)==revision,"duplicate event does not reload history");
    update.userFullInfo.blockList=new TdApi.BlockListStories();cache.onUpdateUserFull(update);
    check(!isMainBlocked(t,77),"stories-only block is not a main blacklist ban");
    t.blockSender(new TdApi.MessageSenderUser(88),new TdApi.BlockListMain(),r->{});
    invalidate(t);t.localClient.answer(new TdApi.Ok());
    check(!isMainBlocked(t,88),"old authorization callback cannot contaminate a new snapshot");
""", sources=event_sources())

    def test_old_event_paths_reproduce_missing_sync(self):
        run_case(r"""
    Tdlib t=ready();t.blockSender(new TdApi.MessageSenderUser(55),new TdApi.BlockListMain(),r->{});
    t.localClient.answer(new TdApi.Ok());
    check(!isMainBlocked(t,55),"old local success path leaves ready snapshot stale");
    UserCache cache=new UserCache(t);TdApi.UpdateUserFullInfo u=new TdApi.UpdateUserFullInfo();
    u.userId=77;u.userFullInfo.blockList=new TdApi.BlockListMain();cache.onUpdateUserFull(u);
    check(!isMainBlocked(t,77),"old profile-only path also leaves snapshot stale");
""", sources=event_sources(True, True))

    def test_short_pages_continue_to_reported_total(self):
        run_case(r"""
    Tdlib t=empty();ensureHiddenUsers(t,membership);t.ui().flush();
    t.answerPage(5,42,43);t.ui().advance(250);
    check(!areHiddenUsersReady(t)&&t.pending.peek().f.offset==2,"short page is not end of the reported list");
    t.answerPage(5,44);t.ui().advance(250);
    check(t.pending.peek().f.offset==3,"offset follows returned entries, not requested page size");
    t.answerPage(5,45,46);t.ui().flush();
    check(areHiddenUsersReady(t)&&isMainBlocked(t,46)&&t.sends==3,"entire list is atomic and terminal total avoids extra request");
    Tdlib empty=empty();ensureHiddenUsers(empty,membership);empty.ui().flush();empty.answerPage(0);empty.ui().flush();
    check(areHiddenUsersReady(empty)&&empty.sends==1,"empty list completes without a loop");
""")

    def test_old_short_page_rule_reproduces_truncation(self):
        sources=lifecycle_sources()
        sources[KEY]=sources[KEY].replace("receivedCount > 0 && messageSenders.totalCount > 0 && nextOffset >= messageSenders.totalCount", "receivedCount > 0 && receivedCount < PAGE_SIZE")
        run_case(r"""
    Tdlib t=empty();ensureHiddenUsers(t,membership);t.ui().flush();t.answerPage(5,42,43);t.ui().flush();
    check(areHiddenUsersReady(t)&&!isMainBlocked(t,46)&&t.sends==1,"old short-page rule publishes an incomplete blacklist");
""",sources=sources)

    def test_refresh_throttle_live_overrides_and_manual_independence(self):
        run_case(r"""
    Tdlib t=ready();MoexConfig.instance().set(t.id(),77);t.ui().flush();int sends=t.sends;
    refreshHiddenUsers(t,false);t.ui().flush();check(t.sends==sends,"recent initial snapshot suppresses automatic refresh");
    t.ui().advance(60000);refreshHiddenUsers(t,false);refreshHiddenUsers(t,false);t.ui().flush();
    check(t.sends==sends+1&&areHiddenUsersReady(t)&&isMainBlocked(t,42),"refresh coalesces and retains known filter while loading");
    onBlockListChanged(t,42,false);onBlockListChanged(t,88,true);
    t.answer(42,55);t.ui().flush();
    check(!isMainBlocked(t,42)&&isMainBlocked(t,55)&&isMainBlocked(t,88),"events received during refresh override older response");
    check(MoexMessageFilter.isShadowBannedUser(t,77),"server refresh does not overwrite manual list");
    long revision=hiddenUsersRevision(t);refreshHiddenUsers(t,true);t.ui().flush();t.answer(55,88);t.ui().flush();
    check(hiddenUsersRevision(t)==revision,"identical refresh does not churn visible history");
    refreshHiddenUsers(t,true);t.ui().flush();t.answer(66);t.ui().flush();
    check(!isMainBlocked(t,55)&&!isMainBlocked(t,88)&&isMainBlocked(t,66),"full refresh reconciles both external block and unblock");
    check(hiddenUsersRevision(t)>revision,"changed snapshot invalidates rendered and unread results");
""")

    def test_incomplete_refresh_and_errors_keep_valid_cache(self):
        run_case(r"""
    Tdlib t=ready();ask(t,-200);success(t);int sends=t.sends;
    refreshHiddenUsers(t,true);t.ui().flush();t.fail(400);t.ui().flush();
    check(areHiddenUsersReady(t)&&isMainBlocked(t,42),"failed refresh preserves known membership");
    ask(t,-200);check(t.sends==sends+1,"failed refresh preserves valid unread result");
    refreshHiddenUsers(t,true);t.ui().advance(15000);t.answerPage(3);t.ui().flush();
    check(areHiddenUsersReady(t)&&isMainBlocked(t,42),"empty page before reported total cannot erase known blacklist");
    t.ui().advance(15000);check(t.pending.size()==1,"incomplete page has one bounded retry");
    t.answerPage(3);t.ui().flush();t.ui().advance(120000);
    check(t.pending.isEmpty()&&isMainBlocked(t,42)&&!accountState(t).hiddenUsersRefreshPending,"repeated incomplete responses stop without clearing cache");
""")

    def test_refresh_shares_native_gate_with_scans_and_timeouts(self):
        run_case(r"""
    Tdlib t=ready();ask(t,-100);check(t.scans.size()==1,"scan owns transport before refresh");
    refreshHiddenUsers(t,true);t.ui().flush();check(t.pending.isEmpty(),"refresh waits for active scan");
    success(t);t.ui().advance(500);check(t.pending.size()==1,"scan completion starts queued refresh");
    t.answerPage(3,42);t.ui().flush();ask(t,-101);t.ui().advance(250);
    check(t.scans.isEmpty()&&t.pending.peek().f.offset==1,"between pages, scan cannot steal refresh transport");
    t.answerPage(3,43,44);t.ui().flush();
    check(isMainBlocked(t,44)&&!accountState(t).hiddenUsersLoading,"refresh completes without a stuck loading flag");
    refreshHiddenUsers(t,true);t.ui().flush();int sends=t.sends;
    t.ui().advance(30000);check(areHiddenUsersReady(t)&&isMainBlocked(t,44)&&accountState(t).apiAttemptTimedOut,"timeout preserves valid cache and native permit");
    for(int i=0;i<20;i++){refreshHiddenUsers(t,true);t.ui().advance(1000);}
    check(t.sends==sends&&t.pending.size()==1,"repeated focus does not overlap timed-out request");
    t.answer(9999);t.ui().flush();
    check(t.pending.size()==1&&!isMainBlocked(t,9999),"real late callback unlocks exactly one fresh reconciliation");
    t.answer(42);t.ui().flush();check(isMainBlocked(t,42)&&!isMainBlocked(t,44),"fresh refresh recovers after timeout");
""")


if __name__ == "__main__":
    unittest.main()
