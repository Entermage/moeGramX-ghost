"""Exercise the production local-notification filter without sending a Telegram request.

The drop method runs unchanged with a topic-settings double. XgramTopicMute is compiled
as a whole with the real TdApi and Tdlib/topic-manager doubles. No notification is
posted and no topic setting is changed on a server.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_forum_scope import method

ROOT = Path(__file__).resolve().parents[1]
MUTE = ROOT / 'app/src/main/java/moe/kirao/mgx/topics/XgramTopicMute.java'
TDAPI = ROOT / 'tdlib/src/main/java/org/drinkless/tdlib/TdApi.java'

HARNESS = '''
import java.util.*;
public class NotificationHarness {
  static class TdApi {
    static class Message {boolean muted;Message(boolean m){muted=m;}}
    static class NotificationTypeNewMessage {Message message;NotificationTypeNewMessage(boolean m){message=new Message(m);}}
    static class Notification {int id;Object type;Notification(int i,Object t){id=i;type=t;}}
    static class NotificationGroupTypeMessages {}
    static class NotificationGroupTypeMentions {}
    static class UpdateNotificationGroup {int notificationGroupId=7;Object type=new NotificationGroupTypeMessages();Notification[] addedNotifications;}
    static class RemoveNotification {int group,id;RemoveNotification(int g,int i){group=g;id=i;}}
  }
  static class Client {List<Integer> removed=new ArrayList<>();void send(TdApi.RemoveNotification q,Object handler){if(q.group!=7)throw new AssertionError("wrong group");removed.add(q.id);}}
  static class Tdlib {Client c=new Client();Client client(){return c;}Object silentHandler(){return null;}}
  static boolean lastMentionGroup;
  static class Mute {static boolean dropsNotification(Tdlib t,TdApi.Message m,boolean mentionGroup){lastMentionGroup=mentionGroup;return m.muted;}}
  final Tdlib tdlib=new Tdlib();
  METHOD
  static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
  static TdApi.Notification message(int id,boolean muted){return new TdApi.Notification(id,new TdApi.NotificationTypeNewMessage(muted));}
  public static void main(String[] args){
    NotificationHarness h=new NotificationHarness();TdApi.UpdateNotificationGroup u=new TdApi.UpdateNotificationGroup();
    check(h.dropMutedTopicNotifications(u)==0,"no additions");u.addedNotifications=new TdApi.Notification[0];check(h.dropMutedTopicNotifications(u)==0,"empty additions");
    u.addedNotifications=new TdApi.Notification[]{message(1,false),message(2,true),new TdApi.Notification(3,new Object()),message(4,true),message(5,false)};
    check(h.dropMutedTopicNotifications(u)==2,"dropped count");
    check(!lastMentionGroup,"Messages group");
    check(u.addedNotifications.length==3,"only muted topic messages are removed");
    check(u.addedNotifications[0].id==1&&u.addedNotifications[1].id==3&&u.addedNotifications[2].id==5,"unmuted/push notifications retain order");
    check(h.tdlib.c.removed.equals(Arrays.asList(2,4)),"dismiss only matching local notification IDs");
    TdApi.Notification[] unchanged=u.addedNotifications;check(h.dropMutedTopicNotifications(u)==0,"no-op count");
    check(u.addedNotifications==unchanged,"no-op retains original array");
    u.addedNotifications=new TdApi.Notification[]{message(6,true)};u.type=new TdApi.NotificationGroupTypeMentions();
    check(h.dropMutedTopicNotifications(u)==1&&lastMentionGroup,"the group type reaches the topic decision");
    check(u.addedNotifications.length==0,"entire muted batch is empty");
    System.out.println("notification filter checks passed");
  }
}
'''

DOUBLES = {
    'androidx/annotation/Nullable.java': 'package androidx.annotation; public @interface Nullable {}',
    'androidx/annotation/IntDef.java': 'package androidx.annotation; public @interface IntDef { int[] value() default {}; boolean flag() default false; boolean open() default false; }',
    'org/thunderdog/challegram/telegram/TdlibForumTopicManager.java': '''package org.thunderdog.challegram.telegram;
import java.util.*; import org.drinkless.tdlib.TdApi;
public class TdlibForumTopicManager {
  public static final class Key { final long chatId; final int forumTopicId;
    public Key (long c, int t) { chatId = c; forumTopicId = t; }
    @Override public boolean equals (Object o) { return o instanceof Key && ((Key) o).chatId == chatId && ((Key) o).forumTopicId == forumTopicId; }
    @Override public int hashCode () { return Objects.hash(chatId, forumTopicId); } }
  public static final class Entry { public final TdApi.ForumTopic value; public Entry (TdApi.ForumTopic v) { value = v; } }
  public interface Callback { void onEntryFound (Entry entry, boolean inPlace); }
  public final Map<Key, TdApi.ForumTopic> known = new HashMap<>(); public final List<Key> requested = new ArrayList<>();
  public final Map<Key, Callback> waiting = new HashMap<>();
  public Entry find (Key key) { TdApi.ForumTopic t = known.get(key); return t != null ? new Entry(t) : null; }
  public Entry findOrRequest (Key key, Callback callback) { requested.add(key); waiting.put(key, callback); return null; }
}''',
    'org/thunderdog/challegram/telegram/Tdlib.java': '''package org.thunderdog.challegram.telegram;
import java.util.*;
public class Tdlib {
  public static final class Ui { public final List<Runnable> queue = new ArrayList<>(); public void post (Runnable r) { queue.add(r); }
    public void flush () { while (!queue.isEmpty()) queue.remove(0).run(); } }
  final int id; final TdlibForumTopicManager topics = new TdlibForumTopicManager(); final Ui ui = new Ui();
  public Tdlib (int id) { this.id = id; } public int id () { return id; }
  public TdlibForumTopicManager topics () { return topics; } public Ui ui () { return ui; }
}''',
    'MuteHarness.java': '''import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.*;
import moe.kirao.mgx.topics.XgramTopicMute;
public class MuteHarness {
  static int checks;
  static void check (boolean b, String m) { checks++; if (!b) throw new AssertionError(m); }
  // Topic settings as TDLib reports them: default fields inherit from the chat.
  static TdApi.ChatNotificationSettings settings (Integer muteFor, Boolean mentionsOff, Boolean pinsOff) {
    TdApi.ChatNotificationSettings s = new TdApi.ChatNotificationSettings();
    s.useDefaultMuteFor = muteFor == null; s.muteFor = muteFor != null ? muteFor : 0;
    s.useDefaultDisableMentionNotifications = mentionsOff == null; s.disableMentionNotifications = mentionsOff != null && mentionsOff;
    s.useDefaultDisablePinnedMessageNotifications = pinsOff == null; s.disablePinnedMessageNotifications = pinsOff != null && pinsOff;
    return s;
  }
  static TdApi.Message message (int topic, boolean mention, boolean pin) {
    TdApi.Message m = new TdApi.Message(); m.chatId = -1001; m.topicId = new TdApi.MessageTopicForum(topic);
    m.containsUnreadMention = mention; m.content = pin ? new TdApi.MessagePinMessage(5) : new TdApi.MessageText();
    return m;
  }
  public static void main (String[] a) {
    Tdlib tdlib = new Tdlib(3), other = new Tdlib(4);
    int forever = Integer.MAX_VALUE;
    XgramTopicMute.onSettings(tdlib, -1001, 1, settings(forever, null, null));
    check(XgramTopicMute.dropsNotification(tdlib, message(1, false, false), false), "muted topic drops ordinary messages");
    check(!XgramTopicMute.dropsNotification(tdlib, message(1, true, false), true), "mention in a muted topic must still notify");
    check(!XgramTopicMute.dropsNotification(tdlib, message(1, false, true), true), "pin in a muted topic still notifies by default");
    check(XgramTopicMute.dropsNotification(tdlib, message(1, true, false), false), "chat-disabled mention follows the topic mute by default");
    XgramTopicMute.onSettings(tdlib, -1001, 2, settings(forever, true, true));
    check(XgramTopicMute.dropsNotification(tdlib, message(2, true, false), true), "topic that disables mentions drops them");
    check(XgramTopicMute.dropsNotification(tdlib, message(2, false, true), true), "topic that disables pins drops them");
    XgramTopicMute.onSettings(tdlib, -1001, 3, settings(0, true, null));
    check(XgramTopicMute.dropsNotification(tdlib, message(3, true, false), true), "explicit mention setting applies to an unmuted topic");
    check(!XgramTopicMute.dropsNotification(tdlib, message(3, false, false), false), "unmuted topic keeps ordinary messages");
    XgramTopicMute.onSettings(tdlib, -1001, 4, settings(forever, false, false));
    check(!XgramTopicMute.dropsNotification(tdlib, message(4, true, false), false), "topic that enables mentions overrides the chat");
    check(!XgramTopicMute.dropsNotification(tdlib, message(4, false, true), false), "topic that enables pins overrides the chat");
    check(XgramTopicMute.dropsNotification(tdlib, message(4, false, false), false), "explicit mention setting does not unmute messages");
    XgramTopicMute.onSettings(tdlib, -1001, 5, settings(null, null, null));
    check(!XgramTopicMute.dropsNotification(tdlib, message(5, false, false), false), "default mute inherits the chat TDLib already applied");
    // Unknown topic: let through, ask once, then filter the next ones.
    check(!XgramTopicMute.dropsNotification(tdlib, message(9, false, false), false), "unknown topic is let through");
    check(!XgramTopicMute.dropsNotification(tdlib, message(9, false, false), false), "unknown topic is let through again");
    tdlib.ui().flush();
    check(tdlib.topics().requested.size() == 1, "settings are asked for once");
    TdApi.ForumTopic topic = new TdApi.ForumTopic(); topic.notificationSettings = settings(forever, null, null);
    tdlib.topics().waiting.get(tdlib.topics().requested.get(0)).onEntryFound(new TdlibForumTopicManager.Entry(topic), false);
    check(XgramTopicMute.dropsNotification(tdlib, message(9, false, false), false), "loaded settings filter the next message");
    check(!XgramTopicMute.dropsNotification(tdlib, message(9, true, false), true), "loaded settings keep mentions");
    check(!XgramTopicMute.dropsNotification(other, message(1, false, false), false), "other account isolated");
    XgramTopicMute.forgetAccount(3);
    check(!XgramTopicMute.isKnown(tdlib, -1001, 1), "closed account forgets topic settings");
    TdApi.Message general = new TdApi.Message(); general.chatId = -1001;
    check(!XgramTopicMute.dropsNotification(tdlib, general, false), "messages without a forum topic are untouched");
    System.out.println("topic notification settings: " + checks + " checks passed");
  }
}''',
}


class ForumNotificationTest(unittest.TestCase):
    def test_muted_topic_notifications_only(self):
        source = (ROOT / 'app/src/main/java/org/thunderdog/challegram/telegram/TdlibNotificationHelper.java').read_text()
        body = method(source, 'private int dropMutedTopicNotifications (').replace('moe.kirao.mgx.topics.XgramTopicMute', 'Mute')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'NotificationHarness.java'
            path.write_text(HARNESS.replace('METHOD', body))
            subprocess.run(['javac', str(path)], check=True, capture_output=True, text=True)
            result = subprocess.run(['java', '-cp', tmp, 'NotificationHarness'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def run_mute(self, mute_source):
        with tempfile.TemporaryDirectory(prefix='topic-mute-') as tmp:
            src = Path(tmp) / 'src'
            for name, text in DOUBLES.items():
                path = src / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            for target, source in ((src / 'org/drinkless/tdlib/TdApi.java', TDAPI.read_text()),
                                   (src / 'moe/kirao/mgx/topics/XgramTopicMute.java', mute_source)):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source)
            classes = Path(tmp) / 'classes'
            subprocess.run(['javac', '-nowarn', '-d', str(classes), *map(str, src.rglob('*.java'))],
                           check=True, capture_output=True, text=True)
            return subprocess.run(['java', '-cp', str(classes), 'MuteHarness'], capture_output=True, text=True)

    def test_topic_mute_mentions_pins_defaults_and_unknown_topics(self):
        result = self.run_mute(MUTE.read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_negative_mentions_follow_topic_mute(self):
        source = MUTE.read_text()
        old = '    if (mentionGroup) {\n      return own == DISABLED;\n    }\n'
        self.assertEqual(source.count(old), 1)
        result = self.run_mute(source.replace(old, ''))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('mention in a muted topic must still notify', result.stderr)


if __name__ == '__main__':
    unittest.main()
