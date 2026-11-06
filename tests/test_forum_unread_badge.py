"""Run the production forum badge: unread topics of a forum and how the chat list keeps them."""
import pathlib
import unittest
import test_history_preview as base

TOPICS = base.ROOT / 'app/src/main/java/moe/kirao/mgx/topics'

STUBS = {
  'android/os/SystemClock.java': 'package android.os; public class SystemClock {public static long now; public static long uptimeMillis(){return now;}}',
  'androidx/annotation/Nullable.java': 'package androidx.annotation; public @interface Nullable {}',
  'androidx/annotation/UiThread.java': 'package androidx.annotation; public @interface UiThread {}',
  'org/drinkless/tdlib/TdApi.java': '''package org.drinkless.tdlib; public class TdApi {
    public static class MessageTopic {}
    public static class MessageTopicForum extends MessageTopic {public int forumTopicId; public MessageTopicForum(int id){forumTopicId=id;}}
    public static class Message {public long id,chatId; public boolean isOutgoing; public MessageTopic topicId; public Object sendingState,schedulingState;}
    public static class ChatNotificationSettings {public boolean useDefaultMuteFor=true; public int muteFor;}
    public static class ForumTopicInfo {public long chatId; public int forumTopicId;}
    public static class ForumTopic {public ForumTopicInfo info=new ForumTopicInfo(); public Message lastMessage; public boolean isPinned; public int unreadCount; public long lastReadInboxMessageId; public ChatNotificationSettings notificationSettings;}
    public static class ForumTopics {public int totalCount; public ForumTopic[] topics;
      public ForumTopics(ForumTopic... t){topics=t;totalCount=t.length;} public ForumTopics(int total,ForumTopic... t){topics=t;totalCount=total;}}
    public static class UpdateForumTopic {public long chatId; public int forumTopicId; public long lastReadInboxMessageId; public ChatNotificationSettings notificationSettings;}
    public static class Chat {public long id,lastReadInboxMessageId; public int unreadCount; public boolean isMarkedAsUnread,viewAsTopics;}
    public static class GetForumTopics {public long chatId,offsetMessageId; public String query; public int offsetDate,offsetForumTopicId,limit;
      public GetForumTopics(long c,String q,int d,long m,int t,int l){chatId=c;query=q;offsetDate=d;offsetMessageId=m;offsetForumTopicId=t;limit=l;}}
    public static class GetForumTopic {public long chatId; public int forumTopicId; public GetForumTopic(long c,int t){chatId=c;forumTopicId=t;}}
    public static class Error {public int code; public String message; public Error(int c,String m){code=c;message=m;}}}''',
  'org/thunderdog/challegram/telegram/ChatListener.java': '''package org.thunderdog.challegram.telegram; import org.drinkless.tdlib.TdApi;
    public interface ChatListener {
    default void onChatReadInbox(long c,long read,int unread,boolean a){}
    default void onForumTopicUpdated(TdApi.UpdateForumTopic u){} }''',
  'org/thunderdog/challegram/telegram/MessageListener.java': '''package org.thunderdog.challegram.telegram; import org.drinkless.tdlib.TdApi;
    public interface MessageListener {
    default void onNewMessage(TdApi.Message m){}
    default void onMessageSendSucceeded(TdApi.Message m,long old){}
    default void onMessagesDeleted(long c,long[] ids){} }''',
  'org/thunderdog/challegram/telegram/TdlibUi.java': '''package org.thunderdog.challegram.telegram; import java.util.*;
    public class TdlibUi {
    static class Task {long at; Runnable r; Task(long a,Runnable x){at=a;r=x;}}
    public final ArrayList<Task> delayed=new ArrayList<>();
    public void post(Runnable r){r.run();}
    public void postDelayed(Runnable r,long ms){delayed.add(new Task(android.os.SystemClock.now+ms,r));}
    public void removeCallbacks(Runnable r){delayed.removeIf(t->t.r==r);}
    public void advance(long ms){android.os.SystemClock.now+=ms; for(Task t:new ArrayList<>(delayed)) if(t.at<=android.os.SystemClock.now&&delayed.remove(t)) t.r.run();}}''',
  'org/thunderdog/challegram/telegram/Tdlib.java': '''package org.thunderdog.challegram.telegram; import org.drinkless.tdlib.TdApi; import java.util.*;
    public class Tdlib {public static int CHAT_MARKED_AS_UNREAD=-1;
    public interface ResultHandler<T> {void onResult(T result, TdApi.Error error);}
    public final TdlibUi ui=new TdlibUi(); public TdlibUi ui(){return ui;} public int id(){return 0;}
    public final HashMap<Long,TdApi.Chat> chats=new HashMap<>(); public final HashSet<Long> forums=new HashSet<>();
    public TdApi.Chat chat(long id){return chats.get(id);} public boolean isForum(long id){return forums.contains(id);}
    public final HashMap<Long,ChatListener> chatListeners=new HashMap<>(); public final HashMap<Long,MessageListener> messageListeners=new HashMap<>();
    public final Listeners l=new Listeners(); public Listeners listeners(){return l;}
    public class Listeners {
      public void subscribeToChatUpdates(long c,ChatListener x){chatListeners.put(c,x);} public void unsubscribeFromChatUpdates(long c,ChatListener x){chatListeners.remove(c,x);}
      public void subscribeToMessageUpdates(long c,MessageListener x){messageListeners.put(c,x);} public void unsubscribeFromMessageUpdates(long c,MessageListener x){messageListeners.remove(c,x);}}}''',
  'me/vkryl/core/reference/ReferenceList.java': '''package me.vkryl.core.reference; import java.util.*;
    public class ReferenceList<T> implements Iterable<T> {private final ArrayList<T> items=new ArrayList<>();
    public void add(T t){if(!items.contains(t))items.add(t);} public void remove(T t){items.remove(t);} public boolean isEmpty(){return items.isEmpty();}
    public void clear(){items.clear();} public Iterator<T> iterator(){return new ArrayList<>(items).iterator();}}''',
  'moe/kirao/mgx/topics/XgramForums.java': '''package moe.kirao.mgx.topics; import org.drinkless.tdlib.TdApi; import org.thunderdog.challegram.telegram.Tdlib;
    public class XgramForums {public static boolean hasForumTabs(Tdlib t,TdApi.Chat c){return false;}
    public static long retryAfterMs(TdApi.Error e,long fallback){return e.code==429?60_000:fallback;}
    public static boolean isTopicGone(TdApi.Error e){return e.code==404||(e.code==400&&e.message!=null&&e.message.contains("TOPIC_ID_INVALID"));}}''',
  'moe/kirao/mgx/topics/ForumTopicList.java': '''package moe.kirao.mgx.topics; import org.drinkless.tdlib.TdApi;
    class ForumTopicList {static int forumTopicId(TdApi.MessageTopic t){return t==null?1:((TdApi.MessageTopicForum)t).forumTopicId;}}''',
  'moe/kirao/mgx/topics/ForumRequests.java': '''package moe.kirao.mgx.topics; import org.drinkless.tdlib.TdApi; import org.thunderdog.challegram.telegram.Tdlib; import java.util.*;
    public class ForumRequests {
    public static final ArrayList<TdApi.GetForumTopics> sent=new ArrayList<>(); public static final ArrayList<Tdlib.ResultHandler<TdApi.ForumTopics>> handlers=new ArrayList<>();
    public static final ArrayList<Object> owners=new ArrayList<>(), cancelled=new ArrayList<>();
    public static void send(Tdlib t,Object owner,TdApi.GetForumTopics q,Tdlib.ResultHandler<TdApi.ForumTopics> h){sent.add(q);handlers.add(h);owners.add(owner);}
    // Single topics: their own list, so page indexes stay as they are.
    public static final ArrayList<TdApi.GetForumTopic> topicSent=new ArrayList<>(); public static final ArrayList<Tdlib.ResultHandler<TdApi.ForumTopic>> topicHandlers=new ArrayList<>();
    public static final ArrayList<Object> topicOwners=new ArrayList<>();
    public static void send(Tdlib t,Object owner,TdApi.GetForumTopic q,Tdlib.ResultHandler<TdApi.ForumTopic> h){topicSent.add(q);topicHandlers.add(h);topicOwners.add(owner);}
    public static void cancel(Tdlib t,Object owner){cancelled.add(owner);}
    public static boolean isClientClosed(TdApi.Error e){return e!=null&&e.code==500;}
    public static void reply(int index,TdApi.ForumTopics r,TdApi.Error e){if(!cancelled.contains(owners.get(index)))handlers.get(index).onResult(r,e);}
    public static void replyTopic(int index,TdApi.ForumTopic r,TdApi.Error e){if(!cancelled.contains(topicOwners.get(index)))topicHandlers.get(index).onResult(r,e);}}''',
}

TOPICS_HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;

public class TopicsHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }
  static java.util.List<Integer> ids(int... ids) { java.util.List<Integer> l = new java.util.ArrayList<>(); for (int id : ids) l.add(id); return l; }
  static TdApi.Message m(int topic, long id, boolean out) {
    TdApi.Message m = new TdApi.Message(); m.chatId = 100; m.id = id; m.isOutgoing = out; m.topicId = new TdApi.MessageTopicForum(topic); return m;
  }
  static TdApi.ForumTopic t(int id, int unread, long read, TdApi.Message last) {
    TdApi.ForumTopic t = new TdApi.ForumTopic(); t.info.chatId = 100; t.info.forumTopicId = id; t.unreadCount = unread; t.lastReadInboxMessageId = read; t.lastMessage = last; return t;
  }
  static TdApi.UpdateForumTopic u(int id, long read, TdApi.ChatNotificationSettings s) {
    TdApi.UpdateForumTopic u = new TdApi.UpdateForumTopic(); u.chatId = 100; u.forumTopicId = id; u.lastReadInboxMessageId = read; u.notificationSettings = s; return u;
  }
  static TdApi.ChatNotificationSettings own(int muteFor) {
    TdApi.ChatNotificationSettings s = new TdApi.ChatNotificationSettings(); s.useDefaultMuteFor = false; s.muteFor = muteFor; return s;
  }

  public static void run() {
    ForumUnreadTopics f = new ForumUnreadTopics();
    check(!f.isLoaded() && f.unreadCount() == 0, "nothing known before a page");
    f.setTopics(new TdApi.ForumTopic[] {
      t(5, 3, 400, m(5, 500, false)),
      t(6, 0, 600, m(6, 600, false)),
      t(7, 2, 650, m(7, 700, true)),   // own last message: nothing unread, as in the topic list
      t(8, 4, 800, m(8, 800, false)),  // read up to the last message: a stale counter
      t(9, 1, 850, m(9, 950, false)),
    }, true);
    check(f.isLoaded() && f.unreadCount() == 2, "own last message or a read up to it counted as unread: " + f.unreadCount());

    check(!f.onMessage(9, m(9, 800, false)), "older message changed the badge");
    check(f.unreadCount() == 2, "older replayed message cleared an unread topic");
    TdApi.Message pending = m(6, 990, false); pending.sendingState = new Object();
    check(!f.onMessage(6, pending) && f.unreadCount() == 2, "pending message counted");
    check(f.onMessage(6, m(6, 1000, false)) && f.unreadCount() == 3, "new incoming message didn't make its topic unread");
    check(f.onMessage(5, m(5, 1001, true)) && f.unreadCount() == 2, "own message left its topic unread");
    check(f.onMessage(42, m(42, 1002, false)) && f.unreadCount() == 3, "message in a topic past the page not counted");

    check(!f.onTopicUpdated(u(9, 900, null)) && f.unreadCount() == 3, "partial read cleared the topic");
    check(f.onTopicUpdated(u(9, 950, null)) && f.unreadCount() == 2, "read up to the last message kept the topic unread");
    f.onTopicUpdated(u(77, 3000, null));
    check(!f.onMessage(77, m(77, 2500, false)) && f.unreadCount() == 2, "message before a known read position counted");

    check(f.unreadInheritingMuteCount() == 2 && f.unreadUnmutedCount() == 0, "mute counters with inherited settings");
    check(f.onTopicUpdated(u(6, 0, own(0))) && f.unreadUnmutedCount() == 1 && f.unreadInheritingMuteCount() == 1, "own unmute not counted");
    check(f.onTopicUpdated(u(6, 0, own(3600))) && f.unreadUnmutedCount() == 0 && f.unreadInheritingMuteCount() == 1, "own mute not counted");

    check(f.needsReloadAfterDelete(new long[] {1, 1000}), "deleted last message of an unread topic not reloaded");
    check(!f.needsReloadAfterDelete(new long[] {600, 950}), "deleted message of a read topic reloaded");
    check(f.removeTopic(42) && f.unreadCount() == 1, "deleted topic still counted");
    check(f.putTopic(t(30, 5, 0, m(30, 20, false))) && f.unreadCount() == 2, "topic loaded by the list not counted");
    f.onMessage(30, m(30, 1100, false));
    check(!f.putTopic(t(30, 0, 1099, m(30, 1099, false))) && f.unreadCount() == 2, "older snapshot cleared a newer unread message");

    f.setTopics(new TdApi.ForumTopic[] {t(5, 1, 0, m(5, 1, false))}, true);
    check(f.unreadCount() == 1, "a new page didn't replace the old one");

    // ---- a first page that isn't every topic: it tells about its own topics only ----
    TdApi.ForumTopic[] first = new TdApi.ForumTopic[20];
    for (int i = 0; i < 20; i++) first[i] = t(i + 1, 0, 1000 + i, m(i + 1, 1000 + i, false));
    ForumUnreadTopics g = new ForumUnreadTopics();
    g.setTopics(first, false);
    check(g.putTopic(t(21, 2, 40, m(21, 50, false))) && g.unreadCount() == 1, "topic loaded by the list past the page not counted");
    g.setTopics(first, false);
    check(g.unreadCount() == 1, "known unread topic past an incomplete page erased");
    TdApi.ForumTopic[] pinned = first.clone();
    pinned[0] = t(1, 0, 5, m(1, 5, false)); pinned[0].isPinned = true;
    check(g.setTopics(pinned, false).isEmpty() && g.unreadCount() == 1, "pinned topic with an old last message made a topic past the page look missing");
    check(g.setTopics(first, false).isEmpty(), "topic past the page with an older last message fetched by itself");
    g.putTopic(t(22, 1, 0, m(22, 1500, false)));
    check(g.unreadCount() == 2, "setup: topic 22 unread");
    // By its last message it would be on the page: deleted elsewhere, or a forum listed by creation date. Not read.
    java.util.List<Integer> unsure = g.setTopics(first, false);
    check(g.unreadCount() == 2, "topic absent from the page it belongs to by its last message dropped");
    check(unsure.equals(ids(22)), "topic absent from the page it belongs to not fetched by itself: " + unsure);
    check(g.removeTopic(22) && g.unreadCount() == 1, "setup: topic 22 gone");
    check(g.needsReloadAfterDelete(new long[] {50}), "deleted last message of a topic past the page not reloaded");
    check(g.unreadCount() == 1, "deleted last message dropped before the page told");
    unsure = g.setTopics(first, false);
    // Three unread, the newest deleted: two are left, the page past it can't tell.
    check(g.unreadCount() == 1, "topic whose last message was deleted dropped past the page");
    check(unsure.equals(ids(21)), "topic whose last message was deleted past the page not fetched by itself: " + unsure);
    check(!g.putTopic(t(21, 3, 40, m(21, 50, false))) && g.unreadCount() == 1, "setup: still unsure");
    check(g.setTopics(first, false).equals(ids(21)), "snapshot with the deleted last message taken as the server's now");
    check(!g.putTopic(t(21, 2, 40, m(21, 49, false))) && g.unreadCount() == 1, "fetched topic with unread messages left not counted");
    check(g.setTopics(first, false).isEmpty(), "fetched topic still unsure");
    check(g.needsReloadAfterDelete(new long[] {49}), "setup: last message deleted again");
    check(g.putTopic(t(21, 0, 48, m(21, 48, false))) && g.unreadCount() == 0, "fetched read topic still counted");
    g.putTopic(t(21, 2, 40, m(21, 50, false)));
    g.setTopics(first, true);
    check(g.unreadCount() == 0, "complete page kept a topic absent from it");

    // ---- an older last message or read position ----
    ForumUnreadTopics h = new ForumUnreadTopics();
    h.setTopics(new TdApi.ForumTopic[] {t(5, 1, 400, m(5, 500, false))}, true);
    check(h.needsReloadAfterDelete(new long[] {500}) && h.unreadCount() == 1, "setup: last message deleted");
    h.setTopics(new TdApi.ForumTopic[] {t(5, 0, 400, m(5, 400, false))}, false);
    check(h.unreadCount() == 0, "page with an older last message after a deletion kept the topic unread");
    h.onMessage(5, m(5, 600, false));
    check(h.needsReloadAfterDelete(new long[] {600}) && h.putTopic(t(5, 0, 400, m(5, 400, false))) && h.unreadCount() == 0,
      "topic list's older last message after a deletion kept the topic unread");
    h.onMessage(5, m(5, 700, false));
    check(h.onTopicUpdated(u(5, 700, null)) && h.unreadCount() == 0, "setup: topic read");
    check(!h.putTopic(t(5, 1, 600, m(5, 700, false))) && h.unreadCount() == 0, "older snapshot unread a topic read since");

    System.out.println("forum unread topics checks passed");
  }
}
'''

BADGES_HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import android.os.SystemClock;
import java.util.*;

public class BadgesHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }
  static class Row implements ForumUnreadBadges.Listener { int changes; public void onForumUnreadTopicsChanged(long c) { changes++; } }
  static TdApi.Chat chat(Tdlib t, long id, int unread) {
    TdApi.Chat c = new TdApi.Chat(); c.id = id; c.unreadCount = unread; c.viewAsTopics = true; c.lastReadInboxMessageId = 10;
    t.chats.put(id, c); t.forums.add(id); return c;
  }
  static TdApi.Message m(long chat, int topic, long id, boolean out) {
    TdApi.Message m = new TdApi.Message(); m.chatId = chat; m.id = id; m.isOutgoing = out; m.topicId = new TdApi.MessageTopicForum(topic); return m;
  }
  static TdApi.ForumTopic t(int id, int unread, long read, long last) {
    TdApi.ForumTopic t = new TdApi.ForumTopic(); t.info.forumTopicId = id; t.unreadCount = unread; t.lastReadInboxMessageId = read;
    TdApi.Message m = new TdApi.Message(); m.id = last; t.lastMessage = m; return t;
  }
  static TdApi.UpdateForumTopic u(long chat, int id, long read) {
    TdApi.UpdateForumTopic u = new TdApi.UpdateForumTopic(); u.chatId = chat; u.forumTopicId = id; u.lastReadInboxMessageId = read; return u;
  }

  public static void run() {
    Tdlib t = new Tdlib();
    TdApi.Chat a = chat(t, 100, 20553), b = chat(t, 200, 5), c = chat(t, 300, 7);
    TdApi.Chat merged = chat(t, 400, 9); merged.viewAsTopics = false;
    check(ForumUnreadBadges.usesTopics(t, 100) && !ForumUnreadBadges.usesTopics(t, 400), "forum shown as merged messages counts its topics");
    t.forums.remove(400L); merged.viewAsTopics = true;
    check(!ForumUnreadBadges.usesTopics(t, 400), "ordinary group counts topics");

    Row ra = new Row(), rb = new Row(), rc = new Row();
    ForumUnreadBadges.attach(t, 100, ra);
    check(ForumRequests.sent.size() == 1 && ForumRequests.sent.get(0).chatId == 100 && ForumRequests.sent.get(0).limit == 20 &&
      ForumRequests.sent.get(0).query.isEmpty() && ForumRequests.sent.get(0).offsetDate == 0, "first page of the newest 20 topics not requested");
    check(ForumUnreadBadges.badgeCount(t, a) == Tdlib.CHAT_MARKED_AS_UNREAD, "server counter shown before the topics are known");
    ForumUnreadBadges.attach(t, 200, rb);
    ForumUnreadBadges.attach(t, 300, rc);
    check(ForumRequests.sent.size() == 1, "two pages in flight");
    ForumUnreadBadges.detach(t, 300, rc);

    t.messageListeners.get(100L).onNewMessage(m(100, 7, 900, false));
    ForumRequests.reply(0, new TdApi.ForumTopics(t(5, 3, 400, 500), t(6, 0, 600, 600), t(7, 0, 800, 800)), null);
    check(ForumUnreadBadges.badgeCount(t, a) == 2, "message during the page load lost: " + ForumUnreadBadges.badgeCount(t, a));
    check(ra.changes == 1, "row not told about the page");
    check(ForumRequests.sent.size() == 2 && ForumRequests.sent.get(1).chatId == 200, "queue didn't move on");

    ForumRequests.reply(1, null, new TdApi.Error(429, "FLOOD_WAIT_60"));
    check(ForumRequests.sent.size() == 2, "page loaded for a forum no row shows");
    check(ForumUnreadBadges.badgeCount(t, b) == Tdlib.CHAT_MARKED_AS_UNREAD, "failed page shown as no unread");
    ForumUnreadBadges.detach(t, 200, rb);
    ForumUnreadBadges.attach(t, 200, rb);
    check(ForumRequests.sent.size() == 2, "retried before the server's wait");
    t.ui.advance(61_000);
    ForumUnreadBadges.detach(t, 200, rb);
    ForumUnreadBadges.attach(t, 200, rb);
    check(ForumRequests.sent.size() == 3 && ForumRequests.sent.get(2).chatId == 200, "not retried after the wait");
    ForumRequests.reply(2, new TdApi.ForumTopics(), null);
    check(ForumUnreadBadges.badgeCount(t, b) == 0, "forum without unread topics shows a badge");
    ForumUnreadBadges.detach(t, 200, rb);
    ForumUnreadBadges.attach(t, 200, rb);
    check(ForumRequests.sent.size() == 3, "known forum loaded again");

    t.chatListeners.get(100L).onForumTopicUpdated(u(100, 5, 500));
    check(ForumUnreadBadges.badgeCount(t, a) == 1, "read topic still counted");
    check(ForumUnreadBadges.isBadgeMuted(t, 100, true) && !ForumUnreadBadges.isBadgeMuted(t, 100, false), "inherited mute");
    TdApi.UpdateForumTopic unmuted = u(100, 7, 800); unmuted.notificationSettings = new TdApi.ChatNotificationSettings();
    unmuted.notificationSettings.useDefaultMuteFor = false; unmuted.notificationSettings.muteFor = 0;
    t.chatListeners.get(100L).onForumTopicUpdated(unmuted);
    check(!ForumUnreadBadges.isBadgeMuted(t, 100, true), "unmuted unread topic in a muted forum drawn muted");

    t.chatListeners.get(100L).onChatReadInbox(100, 10, 20554, false);
    t.ui.advance(3_000);
    check(ForumRequests.sent.size() == 3, "reloaded for a new message's counter");
    t.chatListeners.get(100L).onChatReadInbox(100, 20, 3, false);
    t.chatListeners.get(100L).onChatReadInbox(100, 30, 2, false);
    t.ui.advance(1_000);
    check(ForumRequests.sent.size() == 3, "reloaded before the reads settled");
    t.ui.advance(1_500);
    check(ForumRequests.sent.size() == 4 && ForumRequests.sent.get(3).chatId == 100, "whole chat read not reloaded");
    ForumRequests.reply(3, new TdApi.ForumTopics(t(7, 0, 900, 900)), null);
    check(ForumUnreadBadges.badgeCount(t, a) == 0, "reloaded page not applied");
    ForumUnreadBadges.onTopicLoaded(t, 100, t(31, 4, 0, 1500));
    check(ForumUnreadBadges.badgeCount(t, a) == 1, "topic loaded by the topic list not counted");

    t.messageListeners.get(100L).onNewMessage(m(100, 9, 1000, false));
    t.messageListeners.get(100L).onMessagesDeleted(100, new long[] {1000});
    t.ui.advance(2_500);
    check(ForumRequests.sent.size() == 5, "deleted last message of an unread topic not reloaded");

    ForumUnreadBadges.forgetAccount(t);
    check(ForumRequests.cancelled.size() >= 3 && t.chatListeners.isEmpty() && t.messageListeners.isEmpty(), "closed client kept forums");
    check(ForumUnreadBadges.badgeCount(t, a) == Tdlib.CHAT_MARKED_AS_UNREAD, "closed client kept its counts");
    System.out.println("forum unread badge checks passed");
  }
}
'''

RACES_HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import java.util.*;

public class RacesHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }
  static class Row implements ForumUnreadBadges.Listener { int changes; public void onForumUnreadTopicsChanged(long c) { changes++; } }
  static TdApi.Chat chat(Tdlib t, long id, int unread) {
    TdApi.Chat c = new TdApi.Chat(); c.id = id; c.unreadCount = unread; c.viewAsTopics = true; c.lastReadInboxMessageId = 10;
    t.chats.put(id, c); t.forums.add(id); return c;
  }
  static TdApi.ForumTopic t(int id, int unread, long read, long last) {
    TdApi.ForumTopic t = new TdApi.ForumTopic(); t.info.forumTopicId = id; t.unreadCount = unread; t.lastReadInboxMessageId = read;
    TdApi.Message m = new TdApi.Message(); m.id = last; t.lastMessage = m; return t;
  }
  static TdApi.ForumTopic[] first20() {
    TdApi.ForumTopic[] first = new TdApi.ForumTopic[20];
    for (int i = 0; i < 20; i++) first[i] = t(i + 1, 0, 100 + i, 100 + i);
    return first;
  }
  static TdApi.UpdateForumTopic u(long chat, int id, long read) {
    TdApi.UpdateForumTopic u = new TdApi.UpdateForumTopic(); u.chatId = chat; u.forumTopicId = id; u.lastReadInboxMessageId = read; return u;
  }
  static int sent() { return ForumRequests.sent.size(); }

  public static void run() {
    // ---- a topic past the first page, loaded by the topic list, survives the page's refresh ----
    Tdlib d = new Tdlib(); TdApi.Chat c = chat(d, 100, 1); Row row = new Row();
    ForumUnreadBadges.attach(d, 100, row);
    ForumUnreadBadges.onTopicLoaded(d, 100, t(21, 1, 40, 50)); // before the first page
    ForumRequests.reply(0, new TdApi.ForumTopics(21, first20()), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "topic loaded by the list before the first page lost");
    d.chatListeners.get(100L).onChatReadInbox(100, 11, 1, false);
    d.ui.advance(2001);
    check(sent() == 2, "setup: first page refresh");
    ForumRequests.reply(1, new TdApi.ForumTopics(21, first20()), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "known unread topic past the first page erased by its refresh");
    // The chat read up to its end, nothing left in its counter: TDLib reads no topic for that (mark_dialog_as_read).
    c.unreadCount = 0; c.lastReadInboxMessageId = 3000;
    d.chatListeners.get(100L).onChatReadInbox(100, 3000, 0, false);
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "chat read taken as a read of a topic past the page");
    d.ui.advance(2001);
    check(sent() == 3, "chat read didn't reload the page");
    ForumRequests.reply(2, new TdApi.ForumTopics(21, first20()), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "page after a chat read dropped a topic past it");
    // Its own update reads it.
    d.chatListeners.get(100L).onForumTopicUpdated(u(100, 21, 50));
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "topic's own read update not counted past the page");
    ForumUnreadBadges.forgetAccount(d);

    // ---- a reload asked for while the same page loads ----
    d = new Tdlib(); c = chat(d, 100, 1); row = new Row(); int base = sent();
    ForumUnreadBadges.attach(d, 100, row);
    ForumRequests.reply(base, new TdApi.ForumTopics(t(5, 1, 400, 500)), null);
    d.chatListeners.get(100L).onChatReadInbox(100, 11, 1, false);
    d.ui.advance(2001);
    check(sent() == base + 2, "setup: reload in flight");
    d.messageListeners.get(100L).onMessagesDeleted(100, new long[] {500});
    d.ui.advance(2001);
    d.chatListeners.get(100L).onChatReadInbox(100, 12, 1, false);
    d.ui.advance(2001);
    check(sent() == base + 2, "second request for a page in flight");
    ForumRequests.reply(base + 1, new TdApi.ForumTopics(t(5, 1, 400, 500)), null);
    check(sent() == base + 3, "invalidation while the page loaded lost");
    ForumRequests.reply(base + 2, new TdApi.ForumTopics(t(5, 0, 400, 400)), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "follow-up page not applied");
    d.ui.advance(60_000);
    check(sent() == base + 3, "kept reloading after the follow-up");

    // An error of the follow-up: no reload in the background, the next shown row asks after the wait.
    d.chatListeners.get(100L).onChatReadInbox(100, 13, 1, false);
    d.ui.advance(2001);
    d.chatListeners.get(100L).onChatReadInbox(100, 14, 1, false);
    d.ui.advance(2001);
    ForumRequests.reply(base + 3, new TdApi.ForumTopics(t(5, 0, 400, 400)), null);
    check(sent() == base + 5, "setup: follow-up sent");
    ForumRequests.reply(base + 4, null, new TdApi.Error(429, "FLOOD_WAIT_60"));
    d.ui.advance(120_000);
    check(sent() == base + 5, "failed follow-up retried in the background");
    ForumUnreadBadges.detach(d, 100, row);
    ForumUnreadBadges.attach(d, 100, row);
    check(sent() == base + 6, "stale forum not asked for again once shown after the wait");
    ForumRequests.reply(base + 5, new TdApi.ForumTopics(t(5, 0, 400, 400)), null);
    ForumUnreadBadges.forgetAccount(d);

    // ---- a deletion while the first page loads ----
    d = new Tdlib(); c = chat(d, 100, 1); row = new Row(); base = sent();
    ForumUnreadBadges.attach(d, 100, row);
    d.messageListeners.get(100L).onMessagesDeleted(100, new long[] {500});
    ForumRequests.reply(base, new TdApi.ForumTopics(t(5, 1, 400, 500)), null);
    d.ui.advance(2001);
    check(sent() == base + 2, "deletion while the first page loaded lost");
    ForumRequests.reply(base + 1, new TdApi.ForumTopics(t(5, 0, 400, 400)), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "page after the deletion not applied");
    ForumUnreadBadges.forgetAccount(d);
    System.out.println("forum unread badge race checks passed");
  }
}
'''

OUTSIDE_HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import java.util.*;

/** Topics past the first page and topics deleted here, with the API's order: first page 2000..1981, then older ones. */
public class OutsideHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }
  static class Row implements ForumUnreadBadges.Listener { int changes; public void onForumUnreadTopicsChanged(long c) { changes++; } }
  static TdApi.Chat chat(Tdlib t, long id, int unread) {
    TdApi.Chat c = new TdApi.Chat(); c.id = id; c.unreadCount = unread; c.viewAsTopics = true; c.lastReadInboxMessageId = 10;
    t.chats.put(id, c); t.forums.add(id); return c;
  }
  static TdApi.ForumTopic t(int id, int unread, long read, long last) {
    TdApi.ForumTopic t = new TdApi.ForumTopic(); t.info.forumTopicId = id; t.unreadCount = unread; t.lastReadInboxMessageId = read;
    TdApi.Message m = new TdApi.Message(); m.id = last; t.lastMessage = m; return t;
  }
  static TdApi.UpdateForumTopic u(long chat, int id, long read) {
    TdApi.UpdateForumTopic u = new TdApi.UpdateForumTopic(); u.chatId = chat; u.forumTopicId = id; u.lastReadInboxMessageId = read; return u;
  }
  static TdApi.ForumTopic[] first() {
    TdApi.ForumTopic[] first = new TdApi.ForumTopic[20];
    for (int i = 0; i < 20; i++) first[i] = t(i + 1, 0, 2000 - i, 2000 - i);
    return first;
  }
  static int pages() { return ForumRequests.sent.size(); }
  static int topics() { return ForumRequests.topicSent.size(); }
  static TdApi.Chat c; static Row row;
  /** A forum whose first page is read, topic 21 past it with 3 unread up to 250. */
  static Tdlib setup() {
    Tdlib d = new Tdlib(); c = chat(d, 100, 3); row = new Row();
    ForumUnreadBadges.attach(d, 100, row);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    ForumUnreadBadges.onTopicLoaded(d, 100, t(21, 3, 200, 250));
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "setup: older topic 21 is unread");
    return d;
  }
  /** Its newest message deleted, then the page reloaded and answered without topic 21. */
  static void deleteNewest(Tdlib d) {
    int before = pages();
    d.messageListeners.get(100L).onMessagesDeleted(100, new long[] {250});
    d.ui.advance(2001);
    check(pages() == before + 1, "setup: page reloaded after the deletion");
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
  }

  public static void run() {
    // ---- one of three unread messages past the page deleted ----
    Tdlib d = setup();
    deleteNewest(d);
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "deleting one of three unread messages outside first page falsely clears badge");
    check(topics() == 1 && ForumRequests.topicSent.get(0).chatId == 100 && ForumRequests.topicSent.get(0).forumTopicId == 21,
      "unsure topic past the page not fetched by itself");
    ForumRequests.replyTopic(0, t(21, 2, 200, 240), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "topic with two unread messages left not counted");
    d.ui.advance(600_000);
    check(topics() == 1 && pages() == 2, "kept asking after the topic was known");
    // As the server has it later: read.
    d.messageListeners.get(100L).onMessagesDeleted(100, new long[] {240});
    deleteNewestDone(d, 2);
    ForumRequests.replyTopic(1, t(21, 0, 230, 230), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "topic fetched as read still counted");
    ForumUnreadBadges.forgetAccount(d);

    // ---- the check fails: counted as before, no retry in the background or while hidden ----
    d = setup(); int base = topics();
    deleteNewest(d);
    check(topics() == base + 1, "setup: topic asked for");
    ForumRequests.replyTopic(base, null, new TdApi.Error(429, "FLOOD_WAIT_60"));
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "failed check cleared the topic");
    d.ui.advance(120_000);
    check(topics() == base + 1, "failed check retried in the background");
    ForumUnreadBadges.detach(d, 100, row);
    ForumUnreadBadges.attach(d, 100, row);
    check(topics() == base + 2, "unsure topic not asked for again once shown after the wait");
    ForumRequests.replyTopic(base + 1, null, new TdApi.Error(400, "TOPIC_ID_INVALID"));
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "topic the server doesn't have still counted");
    ForumUnreadBadges.forgetAccount(d);

    // ---- no row shows it when its turn comes: nothing asked until one does ----
    d = setup(); base = topics();
    d.messageListeners.get(100L).onMessagesDeleted(100, new long[] {250});
    d.ui.advance(2001);
    ForumUnreadBadges.detach(d, 100, row);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    d.ui.advance(600_000);
    check(topics() == base && ForumUnreadBadges.badgeCount(d, c) == 1, "hidden forum's topic asked for, or dropped");
    ForumUnreadBadges.attach(d, 100, row);
    check(topics() == base + 1, "shown again, the unsure topic wasn't asked for");
    ForumRequests.replyTopic(base, t(21, 2, 200, 240), null);
    ForumUnreadBadges.forgetAccount(d);

    // ---- a topic read while waiting for its turn: nothing left to ask ----
    d = setup(); base = topics();
    ForumUnreadBadges.onTopicLoaded(d, 100, t(22, 1, 0, 260));
    d.messageListeners.get(100L).onMessagesDeleted(100, new long[] {250, 260});
    d.ui.advance(2001);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    check(topics() == base + 1 && ForumUnreadBadges.badgeCount(d, c) == 2, "setup: first of two unsure topics asked for");
    int other = ForumRequests.topicSent.get(base).forumTopicId == 21 ? 22 : 21;
    d.chatListeners.get(100L).onForumTopicUpdated(u(100, other, 300));
    ForumRequests.replyTopic(base, t(43 - other, 1, 0, 200), null);
    check(topics() == base + 1 && ForumUnreadBadges.badgeCount(d, c) == 1, "topic read meanwhile asked for, or counted");
    ForumUnreadBadges.forgetAccount(d);

    // ---- many unsure topics: a few asked, one at a time; the rest stay counted ----
    d = setup(); base = topics();
    for (int i = 0; i < 12; i++) ForumUnreadBadges.onTopicLoaded(d, 100, t(40 + i, 1, 0, 300 + i));
    long[] newest = new long[12]; for (int i = 0; i < 12; i++) newest[i] = 300 + i;
    d.messageListeners.get(100L).onMessagesDeleted(100, newest);
    d.ui.advance(2001);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 13, "unsure topics dropped: " + ForumUnreadBadges.badgeCount(d, c));
    int asked = 0;
    while (topics() > base + asked) {
      check(topics() == base + asked + 1, "more than one topic asked at once");
      TdApi.GetForumTopic q = ForumRequests.topicSent.get(base + asked);
      ForumRequests.replyTopic(base + asked, t(q.forumTopicId, 1, 0, 290), null);
      asked++;
    }
    check(asked == 8, "unsure topics asked for without a bound: " + asked);
    check(ForumUnreadBadges.badgeCount(d, c) == 13, "fetched topics or the rest not counted");
    ForumUnreadBadges.forgetAccount(d);

    // ---- a forum listed by creation date: a newer unread topic missing from the page is fetched once ----
    d = setup(); base = topics();
    ForumUnreadBadges.onTopicLoaded(d, 100, t(22, 1, 0, 2500));
    d.chatListeners.get(100L).onChatReadInbox(100, 11, 3, false); d.ui.advance(2001);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    check(topics() == base + 1 && ForumRequests.topicSent.get(base).forumTopicId == 22, "topic missing from the page it would be on not fetched");
    ForumRequests.replyTopic(base, t(22, 1, 0, 2500), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 2, "topic the server still has dropped");
    d.chatListeners.get(100L).onChatReadInbox(100, 12, 3, false); d.ui.advance(2001);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    check(topics() == base + 1, "topic the server lists elsewhere fetched again on every page");
    TdApi.Message newer = new TdApi.Message(); newer.chatId = 100; newer.id = 2600; newer.topicId = new TdApi.MessageTopicForum(22);
    d.messageListeners.get(100L).onNewMessage(newer);
    d.chatListeners.get(100L).onChatReadInbox(100, 13, 3, false); d.ui.advance(2001);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    check(topics() == base + 2, "topic with a new last message missing from the page not fetched again");
    ForumRequests.replyTopic(base + 1, null, new TdApi.Error(404, "Not Found"));
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "gone topic still counted");
    ForumUnreadBadges.forgetAccount(d);

    // ---- a topic deleted here isn't brought back by an answer asked for before ----
    d = new Tdlib(); c = chat(d, 100, 1); row = new Row(); base = pages();
    ForumUnreadBadges.attach(d, 100, row);
    ForumUnreadBadges.onTopicLoaded(d, 100, t(5, 1, 400, 500));
    ForumUnreadBadges.onTopicDeleted(d, 100, 5);
    ForumRequests.reply(base, new TdApi.ForumTopics(1, t(5, 1, 400, 500)), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "older in-flight page resurrected locally deleted topic");
    // Deleted while a later page loads.
    ForumUnreadBadges.onTopicLoaded(d, 100, t(6, 1, 600, 700));
    check(ForumUnreadBadges.badgeCount(d, c) == 1, "setup: topic 6 unread");
    d.chatListeners.get(100L).onChatReadInbox(100, 11, 1, false);
    d.ui.advance(2001);
    check(pages() == base + 2, "setup: reload in flight");
    ForumUnreadBadges.onTopicDeleted(d, 100, 6);
    ForumRequests.reply(base + 1, new TdApi.ForumTopics(30, t(6, 1, 600, 700), t(7, 0, 650, 650)), null);
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "later in-flight page resurrected locally deleted topic");
    // The topic list's own late answers.
    ForumUnreadBadges.onTopicLoaded(d, 100, t(6, 1, 600, 700));
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "topic list's late answer resurrected locally deleted topic");
    check(ForumUnreadBadges.isTopicDeleted(d, 100, 6) && !ForumUnreadBadges.isTopicDeleted(d, 200, 6), "deleted topic not known per chat");
    // A forum dropped and followed again still has them: the account keeps them, not the forum.
    ForumUnreadBadges.detach(d, 100, row);
    for (int i = 0; i < 70; i++) { chat(d, 1000 + i, 0); ForumUnreadBadges.attach(d, 1000 + i, new Row()); }
    check(ForumUnreadBadges.isTopicDeleted(d, 100, 6), "deleted topics lost with the forum");
    for (int i = 0; i < 70; i++) ForumUnreadBadges.onTopicDeleted(d, 5000 + i, 1);
    check(!ForumUnreadBadges.isTopicDeleted(d, 100, 6) && ForumUnreadBadges.isTopicDeleted(d, 5069, 1), "deleted topics kept without a bound");
    ForumUnreadBadges.forgetAccount(d);
    check(!ForumUnreadBadges.isTopicDeleted(d, 5069, 1), "closed client kept its deleted topics");
    System.out.println("forum unread badge outside-page checks passed");
  }

  /** A deletion of the newest message again, the page answered, then one topic asked for. */
  static void deleteNewestDone(Tdlib d, int topicsBefore) {
    d.ui.advance(2001);
    ForumRequests.reply(pages() - 1, new TdApi.ForumTopics(30, first()), null);
    check(topics() == topicsBefore, "setup: topic asked for again after its newest message was deleted again");
  }
}
'''

MAIN = 'public class Harness { public static void main(String[] a) { CLASS.run(); } }'


class ForumUnreadBadgeTest(unittest.TestCase):
    run_java = base.HistoryPreviewTest.run_java

    def run_harness(self, harness, name, topics_edit=None, badges_edit=None):
        topics = (TOPICS / 'ForumUnreadTopics.java').read_text()
        badges = (TOPICS / 'ForumUnreadBadges.java').read_text()
        if topics_edit:
            self.assertIn(topics_edit[0], topics)
            topics = topics.replace(*topics_edit)
        if badges_edit:
            self.assertIn(badges_edit[0], badges)
            badges = badges.replace(*badges_edit)
        sources = dict(STUBS)
        sources['moe/kirao/mgx/topics/ForumUnreadTopics.java'] = topics
        sources['moe/kirao/mgx/topics/ForumUnreadBadges.java'] = badges
        sources[f'moe/kirao/mgx/topics/{name}.java'] = harness
        sources['Harness.java'] = MAIN.replace('CLASS', f'moe.kirao.mgx.topics.{name}')
        return self.run_java(sources)

    def topics(self, **edits):
        return self.run_harness(TOPICS_HARNESS, 'TopicsHarness', **edits)

    def badges(self, **edits):
        return self.run_harness(BADGES_HARNESS, 'BadgesHarness', **edits)

    def races(self, **edits):
        return self.run_harness(RACES_HARNESS, 'RacesHarness', **edits)

    def outside(self, **edits):
        return self.run_harness(OUTSIDE_HARNESS, 'OutsideHarness', **edits)

    def rejected(self, run, message, **edits):
        r = run(**edits)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertRegex(r.stderr, message)

    def test_production_topics(self):
        r = self.topics()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('forum unread topics checks passed', r.stdout)

    def test_production_badges(self):
        r = self.badges()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('forum unread badge checks passed', r.stdout)

    def test_production_races(self):
        r = self.races()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('forum unread badge race checks passed', r.stdout)

    def test_production_outside_page(self):
        r = self.outside()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('forum unread badge outside-page checks passed', r.stdout)

    def test_page_clearing_known_topics_rejected(self):
        self.rejected(self.topics, 'known unread topic past an incomplete page erased',
                      topics_edit=('HashMap<Integer, Topic> known = complete || topics.isEmpty() ? null', 'HashMap<Integer, Topic> known = true ? null'))

    def test_partial_page_as_complete_rejected(self):
        self.rejected(self.races, 'topic loaded by the list before the first page lost',
                      badges_edit=('withoutDeleted(forum.chatId, result.topics), complete)', 'withoutDeleted(forum.chatId, result.topics), true)'))

    def test_missing_topic_dropped_rejected(self):
        # Round 1: a topic missing from the page it would be on by its last message was dropped.
        self.rejected(self.topics, 'topic absent from the page it belongs to by its last message dropped',
                      topics_edit=('        topics.put(entry.getKey(), topic);\n', '        if (topic.lastMessageId >= oldestShown) continue;\n        topics.put(entry.getKey(), topic);\n'))

    def test_missing_topic_unchecked_rejected(self):
        self.rejected(self.topics, 'topic absent from the page it belongs to not fetched by itself',
                      topics_edit=('(topic.lastDeleted || (topic.lastMessageId >= oldestShown && !topic.fetched))', '(topic.lastDeleted)'))

    def test_pinned_boundary_rejected(self):
        self.rejected(self.topics, 'pinned topic with an old last message',
                      topics_edit=('if (!forumTopic.isPinned && forumTopic.lastMessage != null) {', 'if (forumTopic.lastMessage != null) {'))

    def test_deleted_last_dropped_rejected(self):
        # Round 1: past an incomplete page, a topic whose last message was deleted became read.
        self.rejected(self.topics, 'topic whose last message was deleted dropped past the page',
                      topics_edit=('        topics.put(entry.getKey(), topic);\n', '        if (topic.lastDeleted) continue;\n        topics.put(entry.getKey(), topic);\n'))

    def test_deleted_last_dropped_production_rejected(self):
        self.rejected(self.outside, 'deleting one of three unread messages outside first page falsely clears badge',
                      topics_edit=('        topics.put(entry.getKey(), topic);\n', '        if (topic.lastDeleted) continue;\n        topics.put(entry.getKey(), topic);\n'))

    def test_deleted_last_unchecked_rejected(self):
        self.rejected(self.topics, 'topic whose last message was deleted past the page not fetched by itself',
                      topics_edit=('            topic.lastDeleted = true;\n', ''))

    def test_unsure_topic_not_fetched_rejected(self):
        self.rejected(self.outside, 'unsure topic past the page not fetched by itself',
                      badges_edit=('      forum.checks.add(forumTopicId);\n', ''))

    def test_unbounded_checks_rejected(self):
        self.rejected(self.outside, 'unsure topics asked for without a bound', badges_edit=('MAX_TOPIC_CHECKS = 8', 'MAX_TOPIC_CHECKS = 100'))

    def test_failed_check_dropped_rejected(self):
        self.rejected(self.outside, 'unsure topic not asked for again once shown after the wait',
                      badges_edit=('        answered = false;\n        forum.retryAfter', '        forum.retryAfter'))

    def test_gone_topic_kept_rejected(self):
        self.rejected(self.outside, "topic the server doesn't have still counted",
                      badges_edit=('} else if (error == null || XgramForums.isTopicGone(error)) {', '} else if (error == null) {'))

    def test_read_topic_still_checked_rejected(self):
        self.rejected(self.outside, 'topic read meanwhile asked for', badges_edit=('if (forum.topics.isUnread(next)) {', 'if (true) {'))

    def test_settled_topic_refetched_rejected(self):
        self.rejected(self.outside, 'topic the server lists elsewhere fetched again on every page',
                      topics_edit=('(topic.lastMessageId >= oldestShown && !topic.fetched)', '(topic.lastMessageId >= oldestShown)'))

    def test_changed_topic_not_refetched_rejected(self):
        self.rejected(self.outside, 'topic with a new last message missing from the page not fetched again',
                      topics_edit=('    topic.lastDeleted = false;\n    topic.fetched = false;\n', '    topic.lastDeleted = false;\n'))

    def test_deleted_topic_page_rejected(self):
        self.rejected(self.outside, 'older in-flight page resurrected locally deleted topic',
                      badges_edit=('withoutDeleted(forum.chatId, result.topics)', 'result.topics'))

    def test_deleted_topic_late_list_rejected(self):
        self.rejected(self.outside, "topic list's late answer resurrected locally deleted topic",
                      badges_edit=('!isTopicDeleted(tdlib, chatId, topic.info.forumTopicId) &&\n        ', ''))

    def test_deleted_topics_unbounded_rejected(self):
        self.rejected(self.outside, 'deleted topics kept without a bound', badges_edit=('MAX_DELETED_TOPICS = 64', 'MAX_DELETED_TOPICS = 1000'))

    def test_read_regression_rejected(self):
        self.rejected(self.topics, 'older snapshot unread a topic read since',
                      topics_edit=('readInboxMessageId = Math.max(readInboxMessageId, topic.lastReadInboxMessageId);', ''))

    def test_chat_read_as_topic_read_rejected(self):
        # Round 1: a read of the chat with nothing left in its counter read every known topic up to it.
        on_chat_read = """  boolean onChatRead (long lastReadInboxMessageId) {
    boolean changed = false;
    for (Topic topic : topics.values()) {
      if (topic.lastMessageId <= lastReadInboxMessageId) {
        topic.lastReadInboxMessageId = Math.max(topic.lastReadInboxMessageId, lastReadInboxMessageId);
        if (topic.unread) { topic.unread = false; changed = true; }
      }
    }
    return changed;
  }

  int unreadCount () {"""
        self.rejected(self.races, 'chat read taken as a read of a topic past the page',
                      topics_edit=('  int unreadCount () {', on_chat_read),
                      badges_edit=('        if (topics.isLoaded() || loading == this) {\n          scheduleReload();',
                                   '        if (topics.isLoaded() && unreadCount == 0 && topics.onChatRead(lastReadInboxMessageId)) publish();\n'
                                   '        if (topics.isLoaded() || loading == this) {\n          scheduleReload();'))

    def test_invalidation_during_load_rejected(self):
        self.rejected(self.races, 'invalidation while the page loaded lost',
                      badges_edit=('forum.stale = forum.invalidation != forum.loadingInvalidation;', 'forum.stale = false;'))

    def test_deletion_during_first_load_rejected(self):
        self.rejected(self.races, 'deletion while the first page loaded lost',
                      badges_edit=('deletedLast |= forum.topics.needsReloadAfterDelete(messageIds);', ''))

    def test_topic_list_before_page_rejected(self):
        self.rejected(self.races, 'topic loaded by the list before the first page lost',
                      badges_edit=('forum.topics.putTopic(topic) && forum.topics.isLoaded()', 'forum.topics.isLoaded() && forum.topics.putTopic(topic)'))

    def test_own_last_message_rule_rejected(self):
        self.rejected(self.topics, 'own last message or a read up to it counted',
                      topics_edit=('(last.isOutgoing || readInboxMessageId >= last.id)', '(false)'))

    def test_replayed_message_rejected(self):
        self.rejected(self.topics, 'older',
                      topics_edit=('} else if (message.id <= topic.lastMessageId) {\n      return false;\n    }', '}'))

    def test_older_snapshot_rejected(self):
        self.rejected(self.topics, 'older snapshot cleared a newer unread message', topics_edit=(
            '} else if (topic.lastDeleted ? lastMessageId == topic.lastMessageId : lastMessageId < topic.lastMessageId) {',
            '} else if (topic.lastDeleted ? lastMessageId == topic.lastMessageId : false) {'))

    def test_snapshot_with_deleted_last_rejected(self):
        self.rejected(self.topics, 'snapshot with the deleted last message taken', topics_edit=(
            '} else if (topic.lastDeleted ? lastMessageId == topic.lastMessageId : lastMessageId < topic.lastMessageId) {',
            '} else if (topic.lastDeleted ? false : lastMessageId < topic.lastMessageId) {'))

    def test_full_read_kept_rejected(self):
        self.rejected(self.topics, 'read up to the last message kept the topic unread',
                      topics_edit=('if (topic.unread && update.lastReadInboxMessageId >= topic.lastMessageId) {', 'if (false) {'))

    def test_one_page_at_a_time_rejected(self):
        self.rejected(self.badges, 'two pages in flight',
                      badges_edit=('while (loading == null && !closed) {', 'while (!closed) {'))

    def test_forum_without_row_rejected(self):
        self.rejected(self.badges, 'page loaded for a forum no row shows',
                      badges_edit=('if (forum.destroyed || forum.listeners.isEmpty()) {', 'if (forum.destroyed) {'))

    def test_message_during_load_rejected(self):
        self.rejected(self.badges, 'message during the page load lost',
                      badges_edit=('pendingMessages.add(message);', ''))

    def test_counter_reload_rejected(self):
        self.rejected(self.badges, "reloaded for a new message's counter",
                      badges_edit=('if (destroyed || lastChatReadInboxMessageId == lastReadInboxMessageId) {', 'if (destroyed) {'))

    def test_flood_wait_rejected(self):
        self.rejected(self.badges, "retried before the server's wait",
                      badges_edit=('|| SystemClock.uptimeMillis() < forum.retryAfter', ''))


if __name__ == '__main__':
    unittest.main()
