import java.util.ArrayList;

/** Production Activity coordinator and MainController lifecycle bodies are injected below. */
public final class StartupNotificationPermissionHarness {
  @interface Nullable { }
  @interface NonNull { }
  interface RunnableBool { void runWithBool (boolean value); }
  static final class Build {
    static final class VERSION { static int SDK_INT = 35; }
    static final class VERSION_CODES { static final int TIRAMISU = 33; }
  }
  static final class Manifest { static final class permission { static final String POST_NOTIFICATIONS = "POST_NOTIFICATIONS"; } }
  static final class Config { static final boolean ENABLE_BASELINE_PROFILE_HOOKS = false; }
  static final class UI {
    static final class State { static final int RESUMED = 1; }
    static final int TEST_MODE_USER = 1, TEST_MODE_NONE = 0;
    static int TEST_MODE;
    static void startNotificationService () { }
  }
  static final class TdlibManager {
    static final int SWITCH_REASON_NAVIGATION = 1;
    void changePreferredAccountId (int id, int reason) { }
  }
  static final class Notifications {
    int grantedEvents;
    void onNotificationPermissionGranted () { grantedEvents++; }
  }
  static final class Tdlib {
    final int account;
    final Notifications notifications = new Notifications();
    final TdlibManager manager = new TdlibManager();
    Tdlib (int account) { this.account = account; }
    int id () { return account; }
    void checkDeadlocks (Runnable callback) { callback.run(); }
    Notifications notifications () { return notifications; }
    TdlibManager context () { return manager; }
  }
  static final class Permissions {
    int prompts;
    boolean granted, immediateDenial;
    RunnableBool pending;
    boolean checkPermission (String permission) { return granted; }
    boolean requestPostNotifications (RunnableBool after) {
      if (Build.VERSION.SDK_INT < 33 || granted) return false;
      prompts++;
      if (immediateDenial) after.runWithBool(false);
      else {
        if (pending != null) throw new AssertionError("concurrent OS permission requests overwrite the callback");
        pending = after;
      }
      return true;
    }
    void complete (boolean grant) {
      granted = grant;
      RunnableBool callback = pending;
      pending = null;
      if (callback != null) callback.runWithBool(grant);
    }
  }
  static class BaseActivity {
    final Permissions permissions = new Permissions();
    Permissions permissions () { return permissions; }
    int getActivityState () { return UI.State.RESUMED; }
    /* ACTIVITY_FIELDS */
    /* ACTIVITY_METHODS */
  }
  static final class MainActivity extends BaseActivity {
    void getMessagesController (Tdlib tdlib, boolean ignored) { }
  }
  static class Controller {
    boolean focused, destroyed;
    public void onFocus () { focused = true; }
    public void onActivityResume () { }
  }
  static final ArrayList<Runnable> delayed = new ArrayList<>();
  static final class Main extends Controller {
    final MainActivity context;
    final Tdlib tdlib;
    int contacts;
    boolean oneShot;
    Main (MainActivity context, Tdlib tdlib) { this.context = context; this.tdlib = tdlib; }
    MainActivity context () { return context; }
    boolean isFocused () { return focused; }
    boolean isDestroyed () { return destroyed; }
    boolean checkSyncAlert () { return false; }
    void addStartupMarker () { }
    void attachRecentChannelsHaptic () { }
    void updateBirthdayReminder (boolean ignored) { }
    void syncContacts (Runnable callback) { contacts++; }
    void runOnUiThreadOptional (Runnable action, Object ignored, long delay) {
      check(delay == 1000L, "test must exercise the existing delayed startup check");
      delayed.add(() -> { if (!destroyed) action.run(); });
    }
    /* MAIN_METHODS */
  }
  static void drain () {
    ArrayList<Runnable> callbacks = new ArrayList<>(delayed);
    delayed.clear();
    for (Runnable callback : callbacks) callback.run();
  }
  static void check (boolean condition, String message) { if (!condition) throw new AssertionError(message); }

  static void denialLoop () {
    MainActivity activity = new MainActivity();
    Main main = new Main(activity, new Tdlib(0));
    main.onFocus(); drain(); activity.permissions.complete(false);
    for (int i = 0; i < 40; i++) {
      main.onActivityResume(); drain(); activity.permissions.complete(false);
    }
    check(activity.permissions.prompts == 1, "resume reopened denied notification permission");
    check(main.contacts == 1, "denial continues contacts once without a startup loop");
    check(main.tdlib.notifications.grantedEvents == 0, "denial must not grant permission");
  }

  static void twoPanes () {
    MainActivity activity = new MainActivity();
    Tdlib account = new Tdlib(0);
    Main original = new Main(activity, account), left = new Main(activity, account);
    original.onFocus(); left.onFocus(); original.onActivityResume(); left.onActivityResume(); drain();
    check(activity.permissions.prompts == 1, "both main controllers share one request");
    check(original.contacts + left.contacts == 0, "contacts wait for notification permission completion");
    activity.permissions.complete(false);
    for (int i = 0; i < 40; i++) { original.onActivityResume(); left.onActivityResume(); drain(); }
    check(activity.permissions.prompts == 1, "both resumed panes cannot re-prompt");
    check(original.contacts + left.contacts == 1, "both panes share one account startup continuation");
  }

  static void accountsAndExplicitRetry () {
    MainActivity activity = new MainActivity();
    Main first = new Main(activity, new Tdlib(0)), second = new Main(activity, new Tdlib(1));
    first.onFocus(); second.onFocus(); drain();
    check(activity.permissions.prompts == 1 && first.contacts + second.contacts == 0, "accounts wait behind one app permission request");
    activity.permissions.complete(false);
    check(first.contacts == 1 && second.contacts == 1, "pending accounts each get one continuation");
    Main third = new Main(activity, new Tdlib(2));
    third.onFocus(); drain();
    check(activity.permissions.prompts == 1 && third.contacts == 1, "later account does not re-prompt automatically");
    int[] explicit = {0};
    activity.permissions().requestPostNotifications(granted -> explicit[0]++);
    check(activity.permissions.prompts == 2, "explicit settings request remains available");
    activity.permissions.complete(true);
    check(explicit[0] == 1, "explicit settings callback still delivered");
  }

  static void grantedAndLegacy () {
    MainActivity activity = new MainActivity();
    activity.permissions.granted = true;
    Main main = new Main(activity, new Tdlib(0));
    main.onFocus(); drain(); main.onActivityResume(); drain();
    check(activity.permissions.prompts == 0 && main.contacts == 1, "existing grant needs no prompt");
    check(main.tdlib.notifications.grantedEvents == 1, "existing grant refreshes notification state once");
    Build.VERSION.SDK_INT = 32;
    MainActivity legacy = new MainActivity();
    Main older = new Main(legacy, new Tdlib(0));
    older.onFocus(); drain(); older.onActivityResume(); drain();
    check(legacy.permissions.prompts == 0 && older.contacts == 1, "legacy Android continues contacts without prompt");
    check(older.tdlib.notifications.grantedEvents == 0, "legacy Android has no POST_NOTIFICATIONS callback");
  }

  static void lifecycle () {
    MainActivity activity = new MainActivity();
    activity.permissions.immediateDenial = true;
    Main main = new Main(activity, new Tdlib(0));
    main.onFocus(); drain(); main.onActivityResume(); drain();
    check(activity.permissions.prompts == 1 && main.contacts == 1, "synchronous denial cannot reopen the request");
    MainActivity replacement = new MainActivity();
    Main next = new Main(replacement, new Tdlib(0));
    next.onFocus(); drain();
    check(replacement.permissions.prompts == 1, "a new Activity has its own startup lifetime");
    next.destroyed = true;
    replacement.permissions.complete(true);
    check(next.contacts == 0 && next.tdlib.notifications.grantedEvents == 0, "destroyed controller ignores delayed permission completion");
  }

  public static void main (String[] args) {
    switch (args[0]) {
      case "denial-loop": denialLoop(); break;
      case "two-panes": twoPanes(); break;
      case "accounts": accountsAndExplicitRetry(); break;
      case "granted-legacy": grantedAndLegacy(); break;
      case "lifecycle": lifecycle(); break;
      default: throw new IllegalArgumentException(args[0]);
    }
    System.out.println(args[0] + ": passed");
  }
}
