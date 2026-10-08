import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

// The production service class and push-start method are inserted unchanged.
// Android lifecycle, time and WorkManager are controlled doubles.
public final class ForegroundServiceHarness {
  @interface NonNull { }
  @interface Nullable { }
  @interface DrawableRes { }
  @interface RequiresApi { int value(); }
  interface RunnableBool { void runWithBool(boolean value); }
  interface IBinder { }
  static class MainActivity { }
  static class Build {
    static class VERSION { static int SDK_INT = 35; }
    static class VERSION_CODES { static final int S = 31, UPSIDE_DOWN_CAKE = 34; }
  }
  static class android {
    static class app {
      static class ForegroundServiceStartNotAllowedException extends RuntimeException { }
    }
  }
  static class R {
    static class drawable { static final int baseline_sync_white_24 = 1; }
    static class string { static final int RetrievingMessages = 1, RetrieveMessagesError = 2, RetrievingText = 3; }
  }
  static class StringUtils { static boolean isEmpty(CharSequence value) { return value == null || value.length() == 0; } }
  static class Log { static String toString(Throwable t) { return t.toString(); } }
  static class Intents { static int mutabilityFlags(boolean value) { return 0; } static String getIntentClassName(Intent i) { return i.clazz.getSimpleName(); } }
  static class TDLib { static class Tag {
    static void notifications(String text, Object... args) { }
    static void notifications(long pushId, int accountId, String text, Object... args) { }
  } }
  static class TdlibAccount { static final int NO_ID = -1; String getLongName() { return "test"; } }
  static class TdlibManager { boolean isMultiUser() { return false; } TdlibAccount account(int id) { return new TdlibAccount(); } }
  static class TdlibNotificationManager { static final int ID_FOREGROUND_PENDING_TASK = 123; }
  static class Lang { static String getString(int id, Object... values) { return "Checking for new messages"; } }
  static class U {
    static String getOtherNotificationChannel() { return "other"; }
    static void startForeground(Service service, int id, Object notification) { service.foreground = true; }
  }
  static class UI { static Context context; static Context getAppContext() { return context; } }
  static class Looper { static Looper getMainLooper() { return new Looper(); } }
  static long now;
  static class Event { long at; Runnable action; Event(long at, Runnable action) { this.at = at; this.action = action; } }
  static final List<Event> events = new ArrayList<>();
  static class Handler {
    Handler(Looper looper) { }
    boolean post(Runnable action) { return postDelayed(action, 0); }
    boolean postDelayed(Runnable action, long delay) { events.add(new Event(now + delay, action)); return true; }
    void removeCallbacks(Runnable action) { events.removeIf(event -> event.action == action); }
  }
  static void flush() {
    while (true) {
      Event next = events.stream().filter(e -> e.at <= now).min(Comparator.comparingLong(e -> e.at)).orElse(null);
      if (next == null) return;
      events.remove(next);
      next.action.run();
    }
  }
  static void advance(long duration) { now += duration; flush(); }
  static class Intent {
    Class<?> clazz;
    String action;
    final Map<String, Object> extras = new HashMap<>();
    Intent() { }
    Intent(Context context, Class<?> clazz) { this.clazz = clazz; }
    Intent setAction(String action) { this.action = action; return this; }
    String getAction() { return action; }
    Intent putExtra(String key, Object value) { extras.put(key, value); return this; }
    String getStringExtra(String key) { return (String) extras.get(key); }
    CharSequence getCharSequenceExtra(String key) { return (CharSequence) extras.get(key); }
    long getLongExtra(String key, long fallback) { return ((Number) extras.getOrDefault(key, fallback)).longValue(); }
    int getIntExtra(String key, int fallback) { return ((Number) extras.getOrDefault(key, fallback)).intValue(); }
  }
  static class Context {
    boolean reject;
    final Map<Class<?>, BaseForegroundService> services = new HashMap<>();
    final Map<Class<?>, Integer> lastIds = new HashMap<>();
    void dispatch(Intent intent) {
      if (reject) throw new android.app.ForegroundServiceStartNotAllowedException();
      int id = lastIds.merge(intent.clazz, 1, Integer::sum);
      new Handler(null).post(() -> {
        BaseForegroundService service = services.get(intent.clazz);
        if (service == null) {
          try { service = (BaseForegroundService) intent.clazz.getDeclaredConstructor().newInstance(); }
          catch (ReflectiveOperationException e) { throw new AssertionError(e); }
          service.context = this;
          services.put(intent.clazz, service);
          service.onCreate();
        }
        service.onStartCommand(intent, 0, id);
      });
    }
  }
  static class ContextCompat { static void startForegroundService(Context context, Intent intent) { context.dispatch(intent); } }
  static class Service extends Context {
    static final int START_NOT_STICKY = 2;
    Context context;
    boolean foreground;
    void onCreate() { }
    void onDestroy() { }
    int onStartCommand(Intent intent, int flags, int id) { return 0; }
    void onTimeout(int id) { }
    IBinder onBind(Intent intent) { return null; }
    void stopForeground(boolean remove) { foreground = false; }
    void stopSelf() { stopSelf(context.lastIds.get(getClass())); }
    void stopSelf(int id) {
      if (context.lastIds.get(getClass()) != id) return;
      new Handler(null).post(() -> {
        context.services.remove(getClass(), this);
        onDestroy();
      });
    }
  }
  static class PendingIntent { static Object getActivity(Context context, int id, Intent intent, int flags) { return null; } }
  static class NotificationCompat { static class Builder {
    Builder(Context context, String channel) { }
    Builder setSmallIcon(int icon) { return this; }
    Builder setContentTitle(CharSequence title) { return this; }
    Builder setContentText(CharSequence text) { return this; }
    Builder setContentIntent(Object intent) { return this; }
    Object build() { return new Object(); }
  } }

  /* BASE_SERVICE */

  static class FetchNotificationService extends BaseForegroundService {
    @Override protected long getTaskTimeoutMillis() { return /* FETCH_TIMEOUT */; }
    @Override protected void onTaskTimeout(long pushId, int accountId) { SyncTask.schedule(pushId, accountId); }
    static boolean startForegroundTask(Context context, CharSequence title, CharSequence text, String channel,
      int icon, long pushId, int accountId, RunnableBool after) {
      return startTask(FetchNotificationService.class, context, title, text, channel, icon, pushId, accountId, after);
    }
    static boolean stopForegroundTask(Context context, long pushId, int accountId) {
      return stopTask(FetchNotificationService.class, context, pushId, accountId);
    }
  }
  static class ContactsService extends BaseForegroundService { }
  static class PushProcessor {
    /* PUSH_START */
  }
  static class SystemClock { static long uptimeMillis() { return now; } }
  enum ExistingWorkPolicy { REPLACE }
  enum NetworkType { CONNECTED }
  enum BackoffPolicy { LINEAR }
  static class Constraints { static class Builder {
    Builder setRequiredNetworkType(NetworkType type) { return this; }
    Constraints build() { return new Constraints(); }
  } }
  static class Data {
    Map<String, Object> values = new HashMap<>();
    static class Builder {
      Data data = new Data();
      Builder putLong(String key, long value) { data.values.put(key, value); return this; }
      Builder putInt(String key, int value) { data.values.put(key, value); return this; }
      Data build() { return data; }
    }
  }
  static class OneTimeWorkRequest {
    static final int MIN_BACKOFF_MILLIS = 10_000;
    Data data;
    Set<String> tags = new HashSet<>();
    static class Builder {
      OneTimeWorkRequest request = new OneTimeWorkRequest();
      Builder(Class<?> clazz) { }
      void setConstraints(Constraints constraints) { }
      void setInputData(Data data) { request.data = data; }
      void addTag(String tag) { request.tags.add(tag); }
      void setBackoffCriteria(BackoffPolicy policy, long delay, TimeUnit unit) { }
      OneTimeWorkRequest build() { return request; }
    }
  }
  static class WorkInfo {
    enum State { RUNNING, ENQUEUED, SUCCEEDED }
    State getState() { return State.ENQUEUED; }
  }
  static class LiveData<T> { T value; LiveData(T value) { this.value = value; } T getValue() { return value; } }
  static class WorkManager {
    static final WorkManager instance = new WorkManager();
    final Map<String, OneTimeWorkRequest> jobs = new HashMap<>();
    static WorkManager getInstance(Context context) { return instance; }
    void cancelAllWorkByTag(String tag) { jobs.values().removeIf(job -> job.tags.contains(tag)); }
    void cancelUniqueWork(String name) { jobs.remove(name); }
    void enqueueUniqueWork(String name, ExistingWorkPolicy policy, OneTimeWorkRequest job) { jobs.put(name, job); }
    LiveData<List<WorkInfo>> getWorkInfosForUniqueWorkLiveData(String name) {
      return new LiveData<>(jobs.containsKey(name) ? List.of(new WorkInfo()) : List.of());
    }
  }
  static class SyncTask {
    /* SYNC_METHODS */
  }

  static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
  static void start(Context c, long push, int account) {
    check(BaseForegroundService.startTask(FetchNotificationService.class, c, "Checking for new messages", null,
      "other", 1, push, account, null), "start rejected");
    flush();
  }
  static void stop(Context c, long push, int account) {
    check(BaseForegroundService.stopTask(FetchNotificationService.class, c, push, account), "stop rejected");
    flush();
  }
  static BaseForegroundService service(Context c) { return c.services.get(FetchNotificationService.class); }
  static int taskCount(Context c) { return service(c) == null ? 0 : service(c).tasks.size(); }
  public static void main(String[] args) {
    Context c = new Context();
    UI.context = c;
    switch (args[0]) {
      case "late-start":
        check(!PushProcessor.showForegroundNotification(c, new TdlibManager(), false, 11, 0, true,
          new CountDownLatch(0)), "unconfirmed start returned success");
        flush();
        check(taskCount(c) == 0, "late service start left an orphan notification");
        break;
      case "interrupted":
        Thread.currentThread().interrupt();
        check(!PushProcessor.showForegroundNotification(c, new TdlibManager(), false, 11, 0, true,
          new CountDownLatch(1)), "interrupted wait returned success");
        Thread.interrupted();
        flush();
        check(taskCount(c) == 0, "interrupted service start left an orphan notification");
        break;
      case "identity":
        start(c, 11, 0); start(c, 12, 1); stop(c, 11, 0);
        check(taskCount(c) == 1 && service(c).tasks.get(0).accountId == 1, "completion removed another account's task");
        stop(c, 11, 0);
        check(taskCount(c) == 1, "duplicate completion removed the remaining task");
        stop(c, 12, 1);
        check(taskCount(c) == 0, "last completion left notification visible");
        break;
      case "duplicate-start":
        start(c, 11, 0); start(c, 11, 0); stop(c, 11, 0);
        check(taskCount(c) == 0, "duplicate start required another stop");
        break;
      case "same-push-other-account":
        start(c, 11, 0); start(c, 11, 1); stop(c, 11, 0);
        check(taskCount(c) == 1 && service(c).tasks.get(0).accountId == 1, "account identity ignored");
        break;
      case "stop-restricted":
        start(c, 11, 0); c.reject = true; stop(c, 11, 0);
        check(taskCount(c) == 0, "active task stop needed another system start exemption");
        break;
      case "deadline":
        start(c, 11, 0); advance(59_999);
        check(taskCount(c) == 1, "task ended early");
        advance(1);
        check(taskCount(c) == 0 && WorkManager.instance.jobs.containsKey("sync:0"), "deadline did not stop and schedule account retry");
        start(c, 12, 0); stop(c, 11, 0);
        check(taskCount(c) == 1, "stale completion removed a newer task");
        break;
      case "staggered-deadlines":
        start(c, 11, 0); advance(30_000); start(c, 12, 1); advance(30_000);
        check(taskCount(c) == 1 && service(c).tasks.get(0).accountId == 1, "deadline removed a newer task");
        advance(30_000); check(taskCount(c) == 0, "second deadline did not stop task");
        break;
      case "cancel-deadline":
        start(c, 11, 0); stop(c, 11, 0); advance(60_000);
        check(WorkManager.instance.jobs.isEmpty(), "completed task still scheduled timeout retry");
        break;
      case "rejected-start-callback":
        AtomicInteger calls = new AtomicInteger(); c.reject = true;
        check(!BaseForegroundService.startTask(FetchNotificationService.class, c, "test", null, "other", 1, 11, 0,
          success -> { check(!success, "rejected request reported success"); calls.incrementAndGet(); }), "rejected request accepted");
        check(calls.get() == 1, "rejected start leaked callback");
        c.reject = false;
        check(BaseForegroundService.startTask(FetchNotificationService.class, c, "test", null, "other", 1, 11, 0,
          success -> check(success, "retry failed")), "retry not accepted");
        flush();
        break;
      case "callback-service-isolation":
        AtomicInteger calls2 = new AtomicInteger();
        BaseForegroundService.startTask(FetchNotificationService.class, c, "test", null, "other", 1, 11, 0, success -> calls2.incrementAndGet());
        BaseForegroundService.startTask(ContactsService.class, c, "test", null, "other", 1, 11, 0, success -> calls2.incrementAndGet());
        flush(); check(calls2.get() == 2, "callbacks collided across services");
        break;
      case "sync-names":
        SyncTask.schedule(11, 0); SyncTask.schedule(12, 1);
        check(WorkManager.instance.jobs.keySet().equals(Set.of("sync:0", "sync:1")), "account retries replaced each other");
        SyncTask.cancel(0);
        check(WorkManager.instance.jobs.keySet().equals(Set.of("sync:1")), "account cancellation used a different name");
        SyncTask.schedule(13, -1);
        check(WorkManager.instance.jobs.keySet().equals(Set.of("sync:all")), "all-account job did not replace specific work");
        SyncTask.cancel(-1); check(WorkManager.instance.jobs.isEmpty(), "all-account cancellation left retries");
        break;
      default: throw new AssertionError(args[0]);
    }
  }
}
