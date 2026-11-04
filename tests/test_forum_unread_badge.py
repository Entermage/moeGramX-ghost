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
    public static class ForumTopic {public ForumTopicInfo info=new ForumTopicInfo(); public Message lastMessage; public int unreadCount; public long lastReadInboxMessageId; public ChatNotificationSettings notificationSettings;}
    public static class ForumTopics {public ForumTopic[] topics; public ForumTopics(ForumTopic... t){topics=t;}}
    public static class UpdateForumTopic {public long chatId; public int forumTopicId; public long lastReadInboxMessageId; public ChatNotificationSettings notificationSettings;}
    public static class Chat {public long id,lastReadInboxMessageId; public int unreadCount; public boolean isMarkedAsUnread,viewAsTopics;}
    public static class GetForumTopics {public long chatId,offsetMessageId; public String query; public int offsetDate,offsetForumTopicId,limit;
      public GetForumTopics(long c,String q,int d,long m,int t,int l){chatId=c;query=q;offsetDate=d;offsetMessageId=m;offsetForumTopicId=t;limit=l;}}
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
    public static long retryAfterMs(TdApi.Error e,long fallback){return e.code==429?60_000:fallback;}}''',
  'moe/kirao/mgx/topics/ForumTopicList.java': '''package moe.kirao.mgx.topics; import org.drinkless.tdlib.TdApi;
    class ForumTopicList {static int forumTopicId(TdApi.MessageTopic t){return t==null?1:((TdApi.MessageTopicForum)t).forumTopicId;}}''',
  'moe/kirao/mgx/topics/ForumRequests.java': '''package moe.kirao.mgx.topics; import org.drinkless.tdlib.TdApi; import org.thunderdog.challegram.telegram.Tdlib; import java.util.*;
    public class ForumRequests {
    public static final ArrayList<TdApi.GetForumTopics> sent=new ArrayList<>(); public static final ArrayList<Tdlib.ResultHandler<TdApi.ForumTopics>> handlers=new ArrayList<>();
    public static final ArrayList<Object> owners=new ArrayList<>(), cancelled=new ArrayList<>();
    public static void send(Tdlib t,Object owner,TdApi.GetForumTopics q,Tdlib.ResultHandler<TdApi.ForumTopics> h){sent.add(q);handlers.add(h);owners.add(owner);}
    public static void cancel(Tdlib t,Object owner){cancelled.add(owner);}
    public static boolean isClientClosed(TdApi.Error e){return e!=null&&e.code==500;}
    public static void reply(int index,TdApi.ForumTopics r,TdApi.Error e){if(!cancelled.contains(owners.get(index)))handlers.get(index).onResult(r,e);}}''',
}

TOPICS_HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;

public class TopicsHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }
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
    });
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
    check(!f.putTopic(t(6, 0, 999, m(6, 999, false))) && f.unreadCount() == 2, "older snapshot cleared a newer unread message");

    f.setTopics(new TdApi.ForumTopic[] {t(5, 1, 0, m(5, 1, false))});
    check(f.unreadCount() == 1, "a new page didn't replace the old one");
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

    def test_own_last_message_rule_rejected(self):
        self.rejected(self.topics, 'own last message or a read up to it counted',
                      topics_edit=('(last.isOutgoing || forumTopic.lastReadInboxMessageId >= last.id)', '(false)'))

    def test_replayed_message_rejected(self):
        self.rejected(self.topics, 'older',
                      topics_edit=('} else if (message.id <= topic.lastMessageId) {\n      return false;\n    }', '}'))

    def test_older_snapshot_rejected(self):
        self.rejected(self.topics, 'older snapshot cleared a newer unread message',
                      topics_edit=('} else if (lastMessageId < topic.lastMessageId) {\n      // Older than a message counted since: a deleted last message loads the page again instead.\n      return false;\n    }', '}'))

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
