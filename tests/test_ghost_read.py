"""Compile actual patched TDLib policy and Java request methods with test doubles.
This does not test Telegram's servers, Android scheduling or genuine accounts.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_chat_navigation import block
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
TD_SOURCE = ROOT / "tdlib/source/td"
JAVA = ROOT / "app/src/main/java/org/thunderdog/challegram/telegram/Tdlib.java"

class GhostReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ghost-patched-policy-")
        cls.patched = Path(cls.temp.name)
        patch = ROOT / "patches/tdlib-ghost-mode.patch"
        for name in re.findall(r"^--- a/(.+)$", patch.read_text(), re.M):
            target = cls.patched / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(["git", "-C", str(TD_SOURCE), "show", "HEAD:" + name]))
        subprocess.run(["git", "apply", str(patch)], cwd=cls.patched, check=True)
        cls.native = cls.patched / "td/telegram/MessagesManager.cpp"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_pending_manual_read_cannot_unlock_other_reads(self):
        method = block(self.native, "static bool is_moex_ghost_read_blocked(")
        harness = r'''
#include <map>
#include <string>
#include <stdexcept>
#include <iostream>
#include <cstdint>
using int64 = int64_t;
struct OptionManager {
  std::map<std::string,bool> flags;
  std::map<std::string,std::string> values;
  bool get_option_boolean(const char *key) { return flags[key]; }
  std::string get_option_string(const char *key) { return values[key]; }
  void set_option_boolean(const char *key, bool value) { flags[key]=value; }
  void set_option_empty(const char *key) { values.erase(key); }
};
enum class DialogType { User, SecretChat, Chat, Channel, None };
struct DialogId { DialogType type; bool broadcast=false; DialogType get_type() { return type; } };
struct DialogManager { bool is_broadcast_channel(DialogId id) { return id.broadcast; } };
struct Td { OptionManager *option_manager_; DialogManager *dialog_manager_; };
#define UNREACHABLE() throw std::runtime_error("unreachable")
__METHOD__
int main() {
  OptionManager options;
  DialogManager dialogs;
  Td td{&options,&dialogs};
  for (auto key : {"x_moex_ghost_read_private","x_moex_ghost_read_groups","x_moex_ghost_read_channels"}) options.flags[key]=true;
  // Simulate an unrelated automatic ViewMessages arriving between SetOption and manual ViewMessages.
  options.flags["x_moex_ghost_read_allow_once"]=true;
  options.values["x_moex_ghost_read_once"]="-100123:52428800";
  int count=0;
  for (auto id : {DialogId{DialogType::User}, DialogId{DialogType::SecretChat}, DialogId{DialogType::Chat},
                 DialogId{DialogType::Channel}, DialogId{DialogType::Channel,true}}) {
    if (!is_moex_ghost_read_blocked(&td,id)) throw std::runtime_error("pending Read until unlocked an unrelated chat");
    count++;
  }
  options.flags["x_moex_ghost_read_groups"]=false;
  if (is_moex_ghost_read_blocked(&td,{DialogType::Chat})) throw std::runtime_error("disabled Ghost scope still blocked");
  std::cout << "Ghost default-read policy: " << count+1 << " checks passed\n";
}
'''.replace("__METHOD__", method)
        source = self.patched / "policy.cpp"
        source.write_text(harness)
        binary = self.patched / "policy"
        subprocess.run(["g++", "-std=c++17", "-o", str(binary), str(source)], check=True)
        subprocess.run([str(binary)], check=True)

    def test_manual_token_is_exact_target_and_single_use(self):
        method = block(self.native, "static bool consume_moex_ghost_read_once(")
        harness = r'''
#include <string>
#include <sstream>
#include <stdexcept>
#include <iostream>
#include <cstdint>
using int64 = int64_t;
struct OptionManager {
  std::string value;
  std::string get_option_string(const char *) { return value; }
  void set_option_empty(const char *) { value.clear(); }
};
struct Td { OptionManager *option_manager_; };
struct Builder {
  std::ostringstream stream;
  template<class T> Builder &operator<<(T v) { stream << v; return *this; }
  friend bool operator!=(const std::string &s, const Builder &b) { return s != b.stream.str(); }
};
#define PSTRING() Builder()
__METHOD__
int main() {
  OptionManager options;
  Td td{&options};
  int checks=0;
  auto expect = [&](bool value) { if(!value) throw std::runtime_error("scoped token failed"); checks++; };
  for (auto token : {"", "true", "-100123", "-100123:52428801", "100123:52428800",
                     "-100123:52428800:extra", " -100123:52428800", "0:52428800", "-100123:0"}) {
    options.value=token;
    expect(!consume_moex_ghost_read_once(&td,-100123,52428800));
  }
  options.value="-100123:52428800";
  expect(!consume_moex_ghost_read_once(&td,-100124,52428800));
  expect(!consume_moex_ghost_read_once(&td,-100123,52428801));
  expect(options.value=="-100123:52428800");
  expect(consume_moex_ghost_read_once(&td,-100123,52428800));
  expect(options.value.empty());
  expect(!consume_moex_ghost_read_once(&td,-100123,52428800));
  options.value="0:0";
  expect(!consume_moex_ghost_read_once(&td,0,0));
  options.value="9223372036854775807:9223372036854775807";
  expect(consume_moex_ghost_read_once(&td,INT64_MAX,INT64_MAX));
  std::cout << "Scoped manual token: " << checks << " production-policy checks passed\n";
}
'''.replace("__METHOD__", method)
        source = self.patched / "token.cpp"
        source.write_text(harness)
        binary = self.patched / "token"
        subprocess.run(["g++", "-std=c++17", "-o", str(binary), str(source)], check=True)
        subprocess.run([str(binary)], check=True)

    def test_only_targeted_history_request_can_bypass_ghost(self):
        view = block(self.native, "Status MessagesManager::view_messages(")
        self.assertIn("force_read && source == MessageSource::DialogHistory", view)
        self.assertIn("message_ids.size() == 1 && message_ids[0] == max_message_id", view)
        self.assertIn('consume_moex_ghost_read_once(td_, get_chat_id_object(dialog_id, "moex manual read"), max_message_id.get())', view)
        self.assertEqual(self.native.read_text().count("read_history_on_server(d, server_message_id, true)"), 1)
        header = (self.native.parent / "MessagesManager.h").read_text()
        self.assertIn("bool allow_in_ghost_mode = false", header)
        read = block(self.native, "void MessagesManager::read_history_on_server(")
        self.assertIn("!allow_in_ghost_mode && is_moex_ghost_read_blocked", read)
        for name in ("MessagesManager.cpp", "ForumTopicManager.cpp", "SavedMessagesManager.cpp"):
            self.assertNotIn("x_moex_ghost_read_allow_once", (self.native.parent / name).read_text())

    def test_manual_read_keeps_same_client_when_account_restarts(self):
        method = block(JAVA, "public void readMessageOnServer (")
        run_java({"ManualReadHarness.java": r'''
import java.util.*;
public class ManualReadHarness {
  static final String MOEX_GHOST_READ_ONCE_OPTION="x_moex_ghost_read_once";
  static class TdApi {
    static class Object { int getConstructor() { return 0; } }
    static class Error extends Object { static final int CONSTRUCTOR=1; Error(int code,String text){} int getConstructor(){return 1;} }
    static class SetOption extends Object { String name; Object value; SetOption(String n,Object v){name=n;value=v;} }
    static class OptionValueBoolean extends Object { boolean value; OptionValueBoolean(boolean v){value=v;} }
    static class OptionValueString extends Object { String value; OptionValueString(String v){value=v;} }
    static class OptionValueEmpty extends Object {}
    static class MessageSourceChatHistory extends Object {}
    static class ViewMessages extends Object {
      long chatId; long[] messageIds; boolean forceRead;
      ViewMessages(long c,long[] m,Object s,boolean force){chatId=c;messageIds=m;forceRead=force;}
    }
  }
  static class Client {
    interface ResultHandler { void onResult(TdApi.Object result); }
    List<TdApi.Object> sent=new ArrayList<>();
    Queue<ResultHandler> pending=new ArrayDeque<>();
    void send(TdApi.Object f,ResultHandler h){sent.add(f);pending.add(h);}
    void reply(){pending.remove().onResult(new TdApi.Object());}
    void reply(TdApi.Object result){pending.remove().onResult(result);}
  }
  Client current=new Client(); int finished, errors, cleanupErrors; boolean throwOnResult;
  Client client(){return current;}
  void enqueueGhostReadOperation(Runnable r){r.run();}
  void finishGhostReadOperation(){finished++;}
  Client.ResultHandler messageHandler(){return r->{
    if(r instanceof TdApi.Error) errors++;
    if(throwOnResult) throw new IllegalStateException("UI handler failed");
  };}
  Client.ResultHandler okHandler(){return r->{if(r instanceof TdApi.Error) cleanupErrors++;};}
  __METHOD__
  static void check(boolean value,String text){if(!value)throw new AssertionError(text);}
  public static void main(String[] args) {
    ManualReadHarness h=new ManualReadHarness();
    Client original=h.current;
    h.readMessageOnServer(-100123L,52428800L);
    h.current=new Client();
    original.reply();
    check(original.sent.size()==2,"manual ViewMessages escaped to a replacement client");
    check(h.current.sent.isEmpty(),"replacement client received an old operation");
    TdApi.SetOption option=(TdApi.SetOption)original.sent.get(0);
    check(option.name.equals(MOEX_GHOST_READ_ONCE_OPTION),"manual permission must be scoped, not global");
    check(((TdApi.OptionValueString)option.value).value.equals("-100123:52428800"),"chat and message must bind the token");
    TdApi.ViewMessages view=(TdApi.ViewMessages)original.sent.get(1);
    check(view.chatId==-100123L && view.messageIds[0]==52428800L && view.forceRead,"manual target changed");
    original.reply();
    check(original.sent.size()==3,"same original client must clear its token");
    check(((TdApi.SetOption)original.sent.get(2)).value instanceof TdApi.OptionValueEmpty,"token not cleared");
    original.reply();
    check(h.finished==1 && h.current.sent.isEmpty(),"queue completion or client isolation failed");
    for(int failureAt=0; failureAt<3; failureAt++){
      ManualReadHarness failure=new ManualReadHarness();
      failure.readMessageOnServer(-100123L,52428800L);
      failure.current.reply(failureAt==0 ? new TdApi.Error(500,"closed") : new TdApi.Object());
      if(failureAt>0) {
        failure.current.reply(failureAt==1 ? new TdApi.Error(400,"missing") : new TdApi.Object());
        check(((TdApi.SetOption)failure.current.sent.get(2)).value instanceof TdApi.OptionValueEmpty,"failed view must clear token");
        failure.current.reply(failureAt==2 ? new TdApi.Error(500,"closed") : new TdApi.Object());
      }
      check(failure.finished==1 && failure.current.pending.isEmpty(),"error stranded operation queue");
      check(failure.errors==(failureAt<2?1:0),"operation error not reported");
      check(failure.cleanupErrors==(failureAt==2?1:0),"cleanup error not reported");
      if(failureAt==0) check(failure.current.sent.size()==1,"failed permission must not read");
    }
    ManualReadHarness throwing=new ManualReadHarness();
    throwing.readMessageOnServer(-100123L,52428800L);
    throwing.throwOnResult=true;
    boolean caught=false;
    try{throwing.current.reply(new TdApi.Error(500,"closed"));}
    catch(IllegalStateException expected){caught=true;}
    check(caught && throwing.finished==1,"throwing UI handler stranded queue");
    System.out.println("Manual-read client isolation and error cleanup: production-method checks passed");
  }
}
'''.replace("__METHOD__", method)}, "ManualReadHarness")

if __name__ == "__main__":
    unittest.main()
