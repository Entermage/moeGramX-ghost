#include <algorithm>
#include <cstdint>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using int32 = int32_t;
using int64 = int64_t;
using std::vector;
using std::unique_ptr;
using std::min;
using std::max;
using std::clamp;
template<class K, class V> using FlatHashMap = std::map<K, V>;
template<class K> using FlatHashSet = std::set<K>;
template<class T, class U> T narrow_cast(U value) { return static_cast<T>(value); }
template<class T> void append(vector<T> &to, vector<T> &&from) {
  to.insert(to.end(), std::make_move_iterator(from.begin()), std::make_move_iterator(from.end()));
}
namespace td {
template<class T, class P> void remove_if(vector<T> &v, P predicate) {
  v.erase(std::remove_if(v.begin(), v.end(), predicate), v.end());
}
template<class T> bool contains(const vector<T> &v, T value) {
  return std::find(v.begin(), v.end(), value) != v.end();
}
template<class T> void unique(vector<T> &v) {
  std::sort(v.begin(), v.end());
  v.erase(std::unique(v.begin(), v.end()), v.end());
}
}
struct Sink { template<class T> Sink &operator<<(const T &) { return *this; } };
Sink checked(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
  return {};
}
#define CHECK(x) checked(static_cast<bool>(x), #x)
#define LOG_CHECK(x) CHECK(x)
#define LOG(...) Sink{}
#define VLOG(...) Sink{}

struct Id {
  int value = 0;
  Id() = default;
  Id(int v) : value(v) {}
  int get() const { return value; }
  bool is_valid() const { return value > 0; }
  bool operator<(Id b) const { return value < b.value; }
  bool operator<=(Id b) const { return value <= b.value; }
  bool operator==(Id b) const { return value == b.value; }
  bool operator!=(Id b) const { return value != b.value; }
};
using NotificationId = Id;
using NotificationGroupId = Id;
enum class DialogType { User, SecretChat };
struct DialogId : Id {
  DialogType kind = DialogType::User;
  DialogId(int v = 1, DialogType k = DialogType::User) : Id(v), kind(k) {}
  DialogType get_type() const { return kind; }
};
enum class NotificationGroupType { Messages, SecretChat, Calls };
struct NotificationGroupKey {
  Id group_id;
  DialogId dialog_id;
  int last_notification_date = 0;
  NotificationGroupKey(Id g = {}, DialogId d = {}, int date = 0)
      : group_id(g), dialog_id(d), last_notification_date(date) {}
  bool operator<(const NotificationGroupKey &other) const {
    return last_notification_date > other.last_notification_date;
  }
};
struct NotificationType {
  Id object;
  bool temporary;
  NotificationType(Id o, bool t = false) : object(o), temporary(t) {}
  bool is_temporary() const { return temporary; }
  bool can_be_delayed() const { return !temporary; }
  Id get_object_id() const { return object; }
};
namespace td_api {
struct Object { virtual ~Object() = default; };
struct notification {
  int id_;
  unique_ptr<Object> type_ = std::make_unique<Object>();
  explicit notification(int id) : id_(id) {}
};
struct Update { virtual ~Update() = default; virtual int get_id() const = 0; };
struct updateNotificationGroup : Update {
  static constexpr int ID = 1;
  int notification_group_id_ = 1, chat_id_ = 1, notification_settings_chat_id_ = 1;
  int notification_sound_id_ = 0, total_count_ = 0;
  unique_ptr<Object> type_ = std::make_unique<Object>();
  vector<unique_ptr<notification>> added_notifications_;
  vector<int> removed_notification_ids_;
  int get_id() const override { return ID; }
};
struct updateNotification : Update {
  static constexpr int ID = 2;
  unique_ptr<notification> notification_;
  int get_id() const override { return ID; }
};
template<class T> using object_ptr = unique_ptr<T>;
}
struct OnlineInfo {
  bool is_online_local = false, is_online_remote = true;
  int was_online_local = 0;
  double was_online_remote = 100000;
};
struct UserManager { OnlineInfo status; OnlineInfo get_my_online_status() { return status; } };
struct DialogManager { void force_create_dialog(DialogId, const char *, bool) {} };
struct Td {
  UserManager users;
  DialogManager dialogs;
  UserManager *user_manager_ = &users;
  DialogManager *dialog_manager_ = &dialogs;
  vector<unique_ptr<td_api::Update>> delivered;
  void send_update(unique_ptr<td_api::Update> update) { delivered.push_back(std::move(update)); }
};
struct Global {
  Td *client = nullptr;
  bool closing = false;
  bool close_flag() const { return closing; }
  double server_time() const { return 100000; }
  Td *td() const { return client; }
} global;
Global *G() { return &global; }
struct Time { static double now() { return 100000; } };
template<class T, class M, class... A> void send_closure(T *target, M method, A &&...args) {
  (target->*method)(std::forward<A>(args)...);
}
struct Timer {
  std::map<int, double> times;
  void set_timeout_at(int id, double when) { times[id] = when; }
  void cancel_timeout(int id, const char * = nullptr) { times.erase(id); }
};
class NotificationManager {
 public:
  struct PendingNotification {
    int date = 0;
    DialogId settings_dialog_id;
    bool disable_notification = false;
    int64 ringtone_id = 0;
    Id notification_id;
    unique_ptr<NotificationType> type;
  };
  using Notification = PendingNotification;
  struct NotificationGroup {
    NotificationGroupType type = NotificationGroupType::Messages;
    vector<Notification> notifications;
    vector<PendingNotification> pending_notifications;
    double pending_notifications_flush_time = 0;
  };
  static constexpr int MIN_NOTIFICATION_DELAY_MS = 1;
  int max_notification_group_count_ = 25;
  int notification_cloud_delay_ms_ = 30000;
  int notification_default_delay_ms_ = 1500;
  int online_cloud_timeout_ms_ = 300000;
  bool is_destroyed_ = false, disabled = false;
  Td client;
  Td *td_ = &client;
  std::map<Id, NotificationGroup> groups_;
  std::map<Id, NotificationGroupKey> group_keys_;
  std::map<int, vector<unique_ptr<td_api::Update>>> pending_updates_;
  Timer flush_pending_notifications_timeout_, flush_pending_updates_timeout_;
  int synchronous_flushes = 0;
  NotificationManager() { global.client = &client; global.closing = false; }
  bool is_disabled() const { return disabled; }
  auto get_group_force(Id group) { return groups_.find(group); }
  auto add_group(NotificationGroupKey key, NotificationGroup group, const char *) {
    group_keys_[key.group_id] = key;
    return groups_.emplace(key.group_id, std::move(group)).first;
  }
  Id get_last_notification_id(const NotificationGroup &group) {
    if (!group.pending_notifications.empty()) return group.pending_notifications.back().notification_id;
    if (!group.notifications.empty()) return group.notifications.back().notification_id;
    return {};
  }
  Id get_last_object_id(const NotificationGroup &group) {
    if (!group.pending_notifications.empty()) return group.pending_notifications.back().type->object;
    if (!group.notifications.empty()) return group.notifications.back().type->object;
    return {};
  }
  NotificationGroupKey get_last_updated_group_key() { return {}; }
  void on_notification_removed(Id) {}
  void on_notification_processed(Id) {}
  void on_delayed_notification_update_count_changed(int, int, const char *) {}
  const void *as_notification_update(td_api::Update *update) { return update; }
  void remove_temporary_notifications(Id id, const char *) {
    auto it = groups_.find(id);
    if (it == groups_.end()) return;
    auto update = std::make_unique<td_api::updateNotificationGroup>();
    update->notification_group_id_ = id.get();
    for (const auto &n : it->second.notifications) {
      if (n.type->temporary) update->removed_notification_ids_.push_back(n.notification_id.get());
    }
    td::remove_if(it->second.notifications, [](const auto &n) { return n.type->temporary; });
    update->total_count_ = static_cast<int>(it->second.notifications.size());
    if (!update->removed_notification_ids_.empty()) pending_updates_[id.get()].push_back(std::move(update));
  }
  void flush_pending_notifications(Id id) {
    ++synchronous_flushes;
    auto &group = groups_.at(id);
    if (group.pending_notifications.empty()) return;
    auto update = std::make_unique<td_api::updateNotificationGroup>();
    update->notification_group_id_ = id.get();
    update->notification_sound_id_ = static_cast<int>(group.pending_notifications.front().ringtone_id);
    for (auto &n : group.pending_notifications) {
      update->added_notifications_.push_back(std::make_unique<td_api::notification>(n.notification_id.get()));
      group.notifications.push_back(std::move(n));
    }
    group.pending_notifications.clear();
    group.pending_notifications_flush_time = 0;
    group_keys_[id] = {id, DialogId{}, 100000};
    update->total_count_ = static_cast<int>(group.notifications.size());
    pending_updates_[id.get()].push_back(std::move(update));
  }
  void seed(int id, int object, bool temporary) {
    if (groups_.empty()) add_group({1, DialogId{}, 100000}, {}, "test setup");
    Notification n;
    n.notification_id = Id(id);
    n.type = std::make_unique<NotificationType>(Id(object), temporary);
    groups_.at(Id(1)).notifications.push_back(std::move(n));
  }
  void receive(int id, int object, bool replacement, int min_delay = 0, bool temporary = false) {
    add_notification(1, NotificationGroupType::Messages, DialogId{}, 100000, DialogId{}, false,
                     replacement ? 0 : 17, min_delay, Id(id),
                     std::make_unique<NotificationType>(Id(object), temporary), replacement, "test");
  }
  int32 get_notification_delay_ms(DialogId, const PendingNotification &, int32) const;
  void add_notification(Id, NotificationGroupType, DialogId, int32, DialogId, bool, int64, int32,
                        Id, unique_ptr<NotificationType>, bool, const char *);
  void flush_pending_updates(int32, const char *);
  void force_flush_pending_updates(Id, const char *);
};

/* PRODUCTION_METHODS */

int main() {
  int checks = 0;
  auto expect = [&](bool condition, const char *why) {
    if (!condition) throw std::runtime_error(why);
    ++checks;
  };
  {
    NotificationManager m;
    m.seed(10, 100, true);
    m.receive(20, 100, true);
    expect(m.client.delivered.size() == 1, "replacement must publish one combined update");
    auto *u = dynamic_cast<td_api::updateNotificationGroup *>(m.client.delivered[0].get());
    expect(u && u->total_count_ == 1, "replacement must never expose an empty group");
    expect(u->added_notifications_.size() == 1 && u->added_notifications_[0]->id_ == 20,
           "formal message missing");
    expect(u->removed_notification_ids_ == vector<int>{10}, "temporary notification must be replaced");
    expect(u->notification_sound_id_ == 0, "replacement must remain silent");
    expect(m.groups_.at(Id(1)).pending_notifications.empty(), "replacement must not wait 30 seconds");
    expect(m.flush_pending_notifications_timeout_.times.empty(), "replacement timer must be cancelled");
  }
  {
    NotificationManager m;
    m.receive(20, 100, false);
    expect(m.client.delivered.empty(), "ordinary cloud delay must remain");
    expect(m.groups_.at(Id(1)).pending_notifications.size() == 1, "ordinary message must stay queued");
    expect(m.flush_pending_notifications_timeout_.times.at(1) == 100030,
           "ordinary cloud delay changed");
    expect(m.synchronous_flushes == 0, "ordinary messages must not force flush");
  }
  {
    NotificationManager m;
    m.seed(9, 99, false);
    m.seed(10, 100, true);
    m.seed(11, 101, true);
    m.receive(20, 100, true);
    m.receive(21, 101, true);
    expect(m.client.delivered.size() == 2, "consecutive replacements missing");
    for (const auto &update : m.client.delivered) {
      auto *u = dynamic_cast<td_api::updateNotificationGroup *>(update.get());
      expect(u && u->total_count_ > 0, "multiple pushes introduced empty group");
      expect(u->notification_sound_id_ == 0, "multiple replacements sounded again");
    }
    expect(m.groups_.at(Id(1)).notifications.size() == 3, "existing notification lost or duplicate added");
  }
  {
    NotificationManager m;
    m.seed(10, 100, true);
    m.remove_temporary_notifications(1, "message already read");
    m.force_flush_pending_updates(1, "message already read");
    auto *u = dynamic_cast<td_api::updateNotificationGroup *>(m.client.delivered.at(0).get());
    expect(u && u->total_count_ == 0 && u->removed_notification_ids_ == vector<int>{10},
           "a genuine removal must still clear the prompt");
  }
  {
    NotificationManager m;
    global.closing = true;
    m.seed(10, 100, true);
    m.receive(20, 100, true);
    expect(m.client.delivered.size() == 1, "closing must not strand a replacement");
    expect(m.groups_.at(Id(1)).pending_notifications.empty(), "closing left a pending replacement");
  }
  {
    NotificationManager m;
    m.client.users.status = {false, false, 0, 0};
    m.receive(20, 100, false, 3000);
    expect(m.flush_pending_notifications_timeout_.times.at(1) == 100003,
           "content-specific minimum delay changed");
  }
  {
    NotificationManager m;
    m.receive(10, 100, false, 0, true);
    expect(m.flush_pending_notifications_timeout_.times.at(1) < 100000.002,
           "initial push must still be immediate");
    expect(m.synchronous_flushes == 0, "initial push was misclassified as a replacement");
  }
  std::cout << "Notification handoff: " << checks << " production-method checks passed\n";
}
