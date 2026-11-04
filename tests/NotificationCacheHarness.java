import java.util.*;

/** Production notification cache methods with Android and TDLib runtime doubles. */
public class NotificationCacheHarness {
  @interface Nullable {}
  static class Type { final int value; Type(int v) { value=v; } int getConstructor() { return value; } }
  static class TdApi {
    static class NotificationGroupType extends Type { NotificationGroupType() { super(0); } }
    static class NotificationGroupTypeMentions extends NotificationGroupType { }
    static class RemoveNotification { final int group, id; RemoveNotification(int g,int i) { group=g; id=i; } }
    static class NotificationTypeNewMessage extends Type {
      static final int CONSTRUCTOR=1; Message message;
      NotificationTypeNewMessage(Message m) { super(CONSTRUCTOR); message=m; }
    }
    static class NotificationTypeNewPushMessage extends Type {
      static final int CONSTRUCTOR=2; long messageId; Object senderId;
      NotificationTypeNewPushMessage(long id) { super(CONSTRUCTOR); messageId=id; senderId=7L; }
    }
    static class Message { long id, chatId=123; Object senderId=7L, content; boolean topicMuted; Message(long i) { id=i; } }
    static class FormattedText { TextEntity[] entities; }
    static class TextEntity { Type type; }
    static class User { boolean isContact=true; }
    static class Notification { int id; Type type; Notification(int i,Type t) { id=i; type=t; } }
    static class UpdateNotificationGroup {
      int notificationGroupId=4, totalCount; long chatId=123, notificationSoundId=0, notificationSettingsChatId=123;
      NotificationGroupType type=new NotificationGroupType();
      Notification[] addedNotifications; int[] removedNotificationIds;
    }
  }
  static class TD { static boolean isVisual(Type type,boolean b) { return false; } }
  static class Td {
    static boolean equalsTo(Object a,Object b) { return Objects.equals(a,b); }
    static TdApi.FormattedText textOrCaption(Object content) { return null; }
    static boolean isEmpty(TdApi.FormattedText text) { return text==null; }
  }
  static class ChatId { static boolean isUserChat(long id) { return true; } }
  static class TDLib { static class Tag { static void notifications(String text,Object... args) {} } }
  static class BitwiseUtils {
    static int splitLongToFirstInt(long value) { return (int)(value>>32); }
    static int splitLongToSecondInt(long value) { return (int)value; }
  }
  static class TdlibSettings {
    final Map<Integer,Long> notificationGroupData=new HashMap<>();
    boolean needMuteNonContacts() { return false; }
    long getNotificationGroupData(int id) { return notificationGroupData.getOrDefault(id,0L); }
    void setNotificationGroupData(int id,int hiddenId,int flags) {
      notificationGroupData.put(id,((long)hiddenId<<32)|(flags&0xffffffffL));
    }
  }
  static class Client {
    final List<Integer> removed=new ArrayList<>();
    void send(TdApi.RemoveNotification query,Object handler) { removed.add(query.id); }
  }
  // Topic settings double; XgramTopicMute's own decision has a production-class suite (test_forum_notification).
  static class Mute {
    static boolean dropsNotification(Tdlib tdlib,TdApi.Message message,boolean mentionGroup) { return message.topicMuted && !mentionGroup; }
  }
  static class Tdlib {
    final Client client=new Client();
    Client client() { return client; }
    Object silentHandler() { return null; }
    TdlibSettings settings=new TdlibSettings();
    TdlibSettings settings() { return settings; }
    boolean isUnauthorized() { return false; }
    TdApi.User chatUser(long id) { return new TdApi.User(); }
  }
  static class NotificationContext { boolean allowNotificationSound(long chatId) { return true; } }
  static class TdlibNotification implements Comparable<TdlibNotification> {
    final TdApi.Notification raw; final TdlibNotificationGroup group; final int id;
    TdlibNotification(Tdlib tdlib,TdApi.Notification raw,TdlibNotificationGroup group) { this.raw=raw; this.group=group; this.id=raw.id; }
    int getId() { return raw.id; }
    long getChatId() { return group.chatId; }
    Type getNotificationContent() { return raw.type; }
    TdlibNotificationGroup group() { return group; }
    void markAsEdited(boolean display) {}
    public int compareTo(TdlibNotification other) { return Integer.compare(getId(),other.getId()); }
    /* NOTIFICATION_HIDDEN_METHOD */
  }
  static class TdlibNotificationGroup {
    static final int FLAG_VISIBLE=2, FLAG_HIDDEN_GLOBALLY=1;
    final Tdlib tdlib; final int id; final long chatId;
    int totalCount, hiddenNotificationId, flags=FLAG_VISIBLE;
    // Mirrors the Android object/database fixture, not its update policy.
    boolean removeDismissed=false;
    final ArrayList<TdlibNotification> notifications=new ArrayList<>();
    TdlibNotificationGroup(Tdlib tdlib,TdApi.UpdateNotificationGroup update) {
      this.tdlib=tdlib; id=update.notificationGroupId; chatId=update.chatId; totalCount=update.totalCount;
      if(update.addedNotifications!=null) for(TdApi.Notification raw:update.addedNotifications)
        notifications.add(new TdlibNotification(tdlib,raw,this));
      Collections.sort(notifications);
      restoreData();
    }
    int getId() { return id; }
    boolean needRemoveDismissedMessages() { return removeDismissed; }
    /* GROUP_METHODS */
  }
  static class Helper {
    final Tdlib tdlib=new Tdlib(); final NotificationContext context=new NotificationContext();
    final ArrayList<TdlibNotification> notifications=new ArrayList<>();
    final Map<Integer,TdlibNotificationGroup> groups=new HashMap<>();
    int hides, displays, alerts; final List<Integer> displayedIds=new ArrayList<>();
    boolean accept(TdApi.NotificationGroupType type) { return true; }
    /* DROP_METHOD */
    boolean allowNotificationPreview() { return true; }
    TdlibNotificationGroup findNotificationGroup(int id) { return groups.get(id); }
    int indexOfNotification(int id) {
      for(int i=0;i<notifications.size();i++) if(notifications.get(i).getId()==id) return i;
      return -1;
    }
    void hideNotificationGroup(TdlibNotificationGroup group) { hides++; }
    void displayNotificationGroup(TdlibNotificationGroup group,boolean alert,long settingsChatId) {
      displays++; if(alert) alerts++; displayedIds.clear();
      for(TdlibNotification notification:group.notifications())
        if(!notification.isHidden()) displayedIds.add(notification.getId());
    }
    /* HELPER_METHODS */
  }
  static TdApi.Notification message(int id,long messageId) {
    return new TdApi.Notification(id,new TdApi.NotificationTypeNewMessage(new TdApi.Message(messageId)));
  }
  static TdApi.Notification push(int id,long messageId) {
    return new TdApi.Notification(id,new TdApi.NotificationTypeNewPushMessage(messageId));
  }
  static TdApi.UpdateNotificationGroup update(int count,TdApi.Notification[] added,int... removed) {
    TdApi.UpdateNotificationGroup update=new TdApi.UpdateNotificationGroup();
    update.totalCount=count; update.addedNotifications=added; update.removedNotificationIds=removed; return update;
  }
  static TdlibNotificationGroup fixture(Helper helper,int id,int count,TdApi.Notification... raws) {
    TdApi.UpdateNotificationGroup initial=update(count,raws); initial.notificationGroupId=id;
    TdlibNotificationGroup group=new TdlibNotificationGroup(helper.tdlib,initial);
    helper.groups.put(id,group); helper.notifications.addAll(group.notifications());
    Collections.sort(helper.notifications); return group;
  }
  static void check(boolean value,String message) { if(!value) throw new AssertionError(message); }
  static void zero(Helper helper,TdlibNotificationGroup group) {
    check(group.notifications().isEmpty(),"authoritative empty group must clear stale 4522");
    check(group.getTotalCount()==0,"empty group count must be zero");
    check(!helper.groups.containsKey(4),"empty group must be removed from helper");
    check(helper.notifications.stream().noneMatch(n->n.group().getId()==4),"global cache must lose every cleared group entry");
    check(helper.hides==1,"empty group must hide the Android notification once");
    check(helper.displays==0,"empty group must not re-post stale notifications");
  }
  static void staleAndCurrent() {
    Helper helper=new Helper();
    TdlibNotificationGroup group=fixture(helper,4,1,message(4522,111),push(4839,222));
    fixture(helper,5,1,message(4500,99));
    helper.updateGroup(update(0,new TdApi.Notification[0],4839));
    zero(helper,group);
    check(helper.notifications.size()==1 && helper.notifications.get(0).getId()==4500,"other group cache must survive");
    check(helper.groups.containsKey(5),"other notification group must survive");
  }
  static void noRemovedIds() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,1,message(4522,111));
    group.hiddenNotificationId=4522; // Existing retention setting makes this individually visible.
    check(!group.notifications().get(0).isHidden(),"retained dismissed message fixture must match private-chat UX");
    TdApi.UpdateNotificationGroup empty=update(0,null); empty.removedNotificationIds=null;
    helper.updateGroup(empty); zero(helper,group);
  }
  static void nonempty() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,1,message(4522,111));
    group.hiddenNotificationId=4522; group.flags=0;
    helper.updateGroup(update(2,new TdApi.Notification[]{push(4839,222)}));
    check(group.notifications().size()==2 && helper.notifications.size()==2,"nonzero update keeps retained history");
    check(helper.displayedIds.equals(Arrays.asList(4522,4839)),"ordinary new push retains dismissed-message display UX");
    helper.updateGroup(update(1,null,4839));
    check(group.notifications().size()==1 && group.notifications().get(0).getId()==4522,"partial deletion preserves retained entry");
    check(helper.groups.get(4)==group && helper.hides==0,"nonzero group must remain available");
    check(helper.notifications.size()==1,"partial deletion must synchronize global cache");
  }
  static void pushReplacement() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,1,push(4839,222));
    group.hiddenNotificationId=4839; group.flags=0;
    helper.updateGroup(update(1,new TdApi.Notification[]{message(4840,222)},4839));
    check(group.hiddenNotificationId==4840 && group.isHidden(),"silent formal replacement must inherit dismissed state");
    check(helper.displays==0 && helper.hides==0,"dismissed push replacement must not display or remove valid group");
    check(group.notifications().size()==1 && group.notifications().get(0).getId()==4840,"replacement must update group cache");
    check(helper.notifications.size()==1 && helper.notifications.get(0).getId()==4840,"replacement must synchronize global cache");
  }
  static void laterNewMessage() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,1,message(4522,111),push(4839,222));
    group.setNotificationData(4839,0);
    long persistedBoundary=helper.tdlib.settings().getNotificationGroupData(4);
    check(group.isHidden(),"dismissed group fixture must start with a persisted hidden boundary");
    TdlibNotificationGroup otherGroup=fixture(helper,5,1,message(4500,99));
    otherGroup.setNotificationData(4500,0);
    long otherGroupData=helper.tdlib.settings().getNotificationGroupData(5);
    Helper otherAccount=new Helper();
    TdlibNotificationGroup accountGroup=fixture(otherAccount,4,1,message(7000,444));
    accountGroup.setNotificationData(7000,0);
    long otherAccountData=otherAccount.tdlib.settings().getNotificationGroupData(4);
    helper.updateGroup(update(0,null,4839)); zero(helper,group);
    check(helper.tdlib.settings().getNotificationGroupData(4)==persistedBoundary,"empty cache cleanup must preserve stored dismissal boundary");
    helper.updateGroup(update(1,new TdApi.Notification[]{message(4840,333)}));
    TdlibNotificationGroup rebuilt=helper.groups.get(4);
    check(rebuilt!=group && rebuilt.hiddenNotificationId==4839,"recreated group must restore persisted hidden boundary");
    check(!rebuilt.isHidden(),"new ID 4840 beyond boundary 4839 must be visible");
    check(helper.notifications.stream().filter(n->n.group().getId()==4).count()==1 && rebuilt.notifications().get(0).getId()==4840,"new activity must not resurrect old 4522");
    check(helper.displayedIds.equals(List.of(4840)),"only the genuinely new notification may display");
    helper.updateGroup(update(0,null,4840));
    check(!helper.groups.containsKey(4) && helper.notifications.stream().noneMatch(n->n.group().getId()==4),"subsequent empty cycle must remain consistent");
    check(helper.hides==2 && helper.displays==1,"read-clear cycles must not re-post old notification");
    check(helper.groups.get(5)==otherGroup && helper.notifications.size()==1 && helper.notifications.get(0).getId()==4500,"other group cache must survive clear and recreation");
    check(helper.tdlib.settings().getNotificationGroupData(5)==otherGroupData,"other group persisted boundary must not change");
    check(otherAccount.groups.get(4)==accountGroup && otherAccount.notifications.size()==1 && otherAccount.notifications.get(0).getId()==7000,"same group ID in another account must remain isolated");
    check(otherAccount.tdlib.settings().getNotificationGroupData(4)==otherAccountData && accountGroup.isHidden(),"other account persisted dismissal must not change");
    check(otherAccount.hides==0 && otherAccount.displays==0,"other account must receive no notification side effects");
  }
  static void unknownEmpty() {
    Helper helper=new Helper();
    helper.updateGroup(update(0,new TdApi.Notification[]{message(4522,111)}));
    check(helper.groups.isEmpty() && helper.notifications.isEmpty(),"zero total cannot create an unknown notification group");
    check(helper.displays==0,"contradictory empty update must not post a notification");
  }
  static TdApi.Notification mutedTopic(int id,long messageId) {
    TdApi.Notification notification=message(id,messageId);
    ((TdApi.NotificationTypeNewMessage)notification.type).message.topicMuted=true; return notification;
  }
  static TdApi.UpdateNotificationGroup sounding(int count,TdApi.Notification[] added,int... removed) {
    TdApi.UpdateNotificationGroup update=update(count,added,removed); update.notificationSoundId=5; return update;
  }
  static void filteredAll() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,1,message(4522,111));
    // TDLib counts and rings for a burst that is entirely in a muted topic.
    helper.updateGroup(sounding(3,new TdApi.Notification[]{mutedTopic(4523,112),mutedTopic(4524,113)}));
    check(helper.tdlib.client.removed.equals(List.of(4523,4524)),"filtered notifications are removed from TDLib");
    check(helper.displays==0 && helper.alerts==0,"fully filtered update must not re-show or ring");
    check(group.getTotalCount()==1,"filtered notifications must not inflate the summary count");
    check(group.notifications().size()==1 && helper.notifications.size()==1,"cache keeps only real notifications");
    helper.updateGroup(update(1,null,4523,4524)); // TDLib's answer to RemoveNotification
    check(helper.displays==0 && helper.hides==0 && group.notifications().size()==1,"the later TDLib removal changes nothing visible");
  }
  static void filteredHidden() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,2,message(4521,110),message(4522,111));
    group.setNotificationData(4522,0);
    check(group.isHidden(),"dismissed group fixture");
    helper.updateGroup(sounding(3,new TdApi.Notification[]{mutedTopic(4523,112)}));
    check(group.isHidden() && helper.displays==0 && helper.alerts==0,"a dismissed group must stay dismissed for filtered messages");
    helper.updateGroup(sounding(2,new TdApi.Notification[]{mutedTopic(4525,114)},4521));
    check(group.isHidden() && helper.displays==0 && helper.alerts==0 && group.getTotalCount()==1,"deletion plus filtered message keeps a dismissed group hidden");
    check(group.notifications().size()==1 && group.notifications().get(0).getId()==4522,"the deletion still applies");
    helper.updateGroup(sounding(1,new TdApi.Notification[]{mutedTopic(4526,115)},4522));
    check(!helper.groups.containsKey(4) && helper.hides==1 && helper.displays==0,"an emptied group is hidden without ringing");
  }
  static void filteredPartial() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,1,message(4522,111));
    helper.updateGroup(sounding(3,new TdApi.Notification[]{mutedTopic(4523,112),message(4524,113)}));
    check(helper.displays==1 && helper.alerts==1,"a real new message in the same update still alerts once");
    check(group.getTotalCount()==2,"count excludes only the filtered notification");
    check(helper.displayedIds.equals(List.of(4522,4524)),"only real notifications are shown");
  }
  static void pureDeletion() {
    Helper helper=new Helper(); TdlibNotificationGroup group=fixture(helper,4,2,message(4522,111),message(4523,112));
    helper.updateGroup(update(1,null,4523));
    check(helper.tdlib.client.removed.isEmpty(),"a deletion is never filtered");
    check(group.notifications().size()==1 && group.getTotalCount()==1 && helper.displays==1 && helper.alerts==0,"deletion updates silently");
  }
  static void mentionsGroup() {
    Helper helper=new Helper();
    TdApi.UpdateNotificationGroup mention=sounding(1,new TdApi.Notification[]{mutedTopic(4600,200)});
    mention.type=new TdApi.NotificationGroupTypeMentions(); mention.notificationGroupId=9;
    helper.updateGroup(mention);
    check(helper.tdlib.client.removed.isEmpty() && helper.groups.containsKey(9),"the Mentions group is decided by mention settings, not the topic mute");
    check(helper.displays==1 && helper.alerts==1,"mention in a muted topic still notifies");
  }
  public static void main(String[] args) {
    switch(args[0]) {
      case "stale-and-current": staleAndCurrent(); break;
      case "no-removed-ids": noRemovedIds(); break;
      case "nonempty": nonempty(); break;
      case "push-replacement": pushReplacement(); break;
      case "later-new-message": laterNewMessage(); break;
      case "unknown-empty": unknownEmpty(); break;
      case "filtered-all": filteredAll(); break;
      case "filtered-hidden": filteredHidden(); break;
      case "filtered-partial": filteredPartial(); break;
      case "pure-deletion": pureDeletion(); break;
      case "mentions-group": mentionsGroup(); break;
      default: throw new AssertionError("unknown scenario: "+args[0]);
    }
    System.out.println("Notification cache production-method scenario passed: "+args[0]);
  }
}
