"""Run production interaction/read methods with client doubles; not server E2E."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from test_chat_navigation import block
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java"
TDLIB = JAVA / "org/thunderdog/challegram/telegram/Tdlib.java"
CONFIG = JAVA / "moe/kirao/mgx/MoexConfig.java"


class ReadOnInteractTest(unittest.TestCase):
    def test_production_interactions_and_privacy_boundaries(self):
        methods = "\n".join(block(TDLIB, signature) for signature in (
            "public <T extends TdApi.Object> void sendMessageInteraction (",
            "private boolean canReadOnInteract (",
            "private void readMessageOnInteraction (",
            "private void readSentMessageOnInteraction (",
            "public void readMessageOnServer (",
            "private void readMessageOnServer (",
            "private void enqueueGhostReadOperation (",
            "private void finishGhostReadOperation (",
        )).replace("@Nullable ", "").replace("@NonNull ", "")
        run_java({"InteractionHarness.java": r'''
import java.util.*;
public class InteractionHarness {
  static class MoexConfig { static boolean ghostReadOnInteract; }
  static class ChatId { static boolean isSecret(long id) { return id == -999; } }
  static final String MOEX_GHOST_READ_ONCE_OPTION="x_moex_ghost_read_once";
  static class TdApi {
    static class Object { int getConstructor() { return 0; } }
    static class Function<T extends Object> extends Object {}
    static class Ok extends Object {}
    static class Error extends Object { static final int CONSTRUCTOR=1; int getConstructor(){ return 1; } }
    static class AddMessageReaction extends Function<Ok> { long chatId, messageId; AddMessageReaction(long c,long m){chatId=c;messageId=m;} }
    static class RemoveMessageReaction extends Function<Ok> { long chatId, messageId; RemoveMessageReaction(long c,long m){chatId=c;messageId=m;} }
    static class SetPollAnswer extends Function<Ok> { long chatId, messageId; SetPollAnswer(long c,long m){chatId=c;messageId=m;} }
    static class SendChatAction extends Function<Ok> {}
    static class ViewMessages extends Function<Ok> {
      long chatId; long[] messageIds; boolean forceRead;
      ViewMessages(long c,long[] m,MessageSourceChatHistory s,boolean f){chatId=c;messageIds=m;forceRead=f;}
    }
    static class MessageSourceChatHistory {}
    static class SetOption extends Function<Ok> { String name; Object value; SetOption(String n,Object v){name=n;value=v;} }
    static class OptionValueString extends Object { String value; OptionValueString(String v){value=v;} }
    static class OptionValueEmpty extends Object {}
    static class Message extends Object {
      long chatId=-100, id=52428800; boolean isOutgoing=true, isFromOffline;
      Object sendingState, schedulingState;
    }
  }
  static class Client {
    interface ResultHandler { void onResult(TdApi.Object result); }
    final List<TdApi.Function<?>> sent=new ArrayList<>();
    final Queue<ResultHandler> pending=new ArrayDeque<>();
    <T extends TdApi.Object> void send(TdApi.Function<T> f,ResultHandler h){ sent.add(f); if(h!=null) pending.add(h); }
    void reply(TdApi.Object r){ pending.remove().onResult(r); }
    void flush(){ while(!pending.isEmpty()) reply(new TdApi.Ok()); }
    long views(){return sent.stream().filter(f->f instanceof TdApi.ViewMessages).count();}
  }
  final Object ghostReadOperationLock=new Object();
  final ArrayDeque<Runnable> ghostReadOperations=new ArrayDeque<>();
  boolean ghostReadOperationActive;
  Client current=new Client();
  boolean ghost=true; final Set<Long> enabledScopes=new HashSet<>(Arrays.asList(42L,-100L,-200L,-999L,1L));
  int reported, callbackCount;
  interface LocalReadCondition { boolean isValid(); }
  Client client(){return current;}
  boolean ownsClient(Client c){return c==current;}
  boolean isGhostReadEnabled(long c){return ghost && enabledScopes.contains(c);}
  boolean isSelfChat(long c){return c==1;}
  Client.ResultHandler okHandler(){return r->{if(r instanceof TdApi.Error) reported++;};}
  Client.ResultHandler messageHandler(){return okHandler();}
  __METHODS__
  static int checks;
  static void check(boolean b,String why){checks++;if(!b)throw new AssertionError(why);}
  static InteractionHarness fresh(){MoexConfig.ghostReadOnInteract=true;return new InteractionHarness();}
  static void target(Client c,long chat,long id){
    check(c.views()==1,"expected exactly one read");
    TdApi.ViewMessages v=(TdApi.ViewMessages)c.sent.stream().filter(f->f instanceof TdApi.ViewMessages).findFirst().get();
    check(v.chatId==chat && v.messageIds.length==1 && v.messageIds[0]==id && v.forceRead,"wrong read target");
    TdApi.SetOption start=(TdApi.SetOption)c.sent.stream().filter(f->f instanceof TdApi.SetOption).findFirst().get();
    check(start.name.equals(MOEX_GHOST_READ_ONCE_OPTION) && ((TdApi.OptionValueString)start.value).value.equals(chat+":"+id),"not a target-bound permission");
    check(((TdApi.SetOption)c.sent.get(c.sent.size()-1)).value instanceof TdApi.OptionValueEmpty,"permission not cleaned up");
  }
  static void noRead(Client c,String why){check(c.sent.stream().noneMatch(f->f instanceof TdApi.ViewMessages || f instanceof TdApi.SetOption),why);}
  public static void main(String[] args){
    for(long chat:new long[]{42,-100,-200}) for(int kind=0;kind<3;kind++){
      InteractionHarness h=fresh();
      TdApi.Function<TdApi.Ok> action=kind==0?new TdApi.AddMessageReaction(chat,70):kind==1?new TdApi.RemoveMessageReaction(chat,70):new TdApi.SetPollAnswer(chat,70);
      h.sendMessageInteraction(action,r->h.callbackCount++);
      noRead(h.current,"request start must not read");
      h.current.flush();target(h.current,chat,70);check(h.callbackCount==1,"original callback lost");
      check(!h.ghostReadOperationActive,"queue stuck");
    }
    for(int mode=0;mode<7;mode++){
      InteractionHarness h=fresh();long chat=mode==3?1:mode==4?-999:mode==5?0:-100;
      if(mode==0)MoexConfig.ghostReadOnInteract=false;
      if(mode==1)h.ghost=false;
      if(mode==2)h.enabledScopes.clear();
      h.sendMessageInteraction(new TdApi.AddMessageReaction(chat,70),r->h.callbackCount++);
      h.current.reply(mode==6?new TdApi.Error():new TdApi.Ok());
      noRead(h.current,"disabled/secret/self/failed action must not read");check(h.callbackCount==1,"callback missing");
    }
    InteractionHarness typing=fresh();typing.sendMessageInteraction(new TdApi.SendChatAction(),null);noRead(typing.current,"typing is not interaction");
    for(boolean replace:new boolean[]{false,true}){
      InteractionHarness h=fresh();Client original=h.current;
      h.sendMessageInteraction(new TdApi.SetPollAnswer(-100,70),null);
      if(replace)h.current=new Client();else MoexConfig.ghostReadOnInteract=false;
      original.flush();noRead(original,"late interaction callback escaped guard");noRead(h.current,"new client touched");
    }
    InteractionHarness lateEnable=fresh();MoexConfig.ghostReadOnInteract=false;
    lateEnable.sendMessageInteraction(new TdApi.AddMessageReaction(-100,70),null);MoexConfig.ghostReadOnInteract=true;
    lateEnable.current.flush();noRead(lateEnable.current,"enabling must not retrospectively read pending reactions");
    for(int field=0;field<5;field++){
      InteractionHarness h=fresh();TdApi.Message m=new TdApi.Message();
      if(field==1)m.isOutgoing=false;if(field==2)m.sendingState=new TdApi.Object();
      if(field==3)m.schedulingState=new TdApi.Object();if(field==4)m.isFromOffline=true;
      h.readSentMessageOnInteraction(m);h.current.flush();
      if(field==0)target(h.current,-100,m.id);else noRead(h.current,"non-success/scheduled/automatic message read");
    }
    InteractionHarness zero=fresh();zero.readMessageOnInteraction(zero.current,-100,0);noRead(zero.current,"zero message");
    InteractionHarness queued=fresh();queued.ghostReadOperationActive=true;
    queued.readSentMessageOnInteraction(new TdApi.Message());MoexConfig.ghostReadOnInteract=false;
    queued.finishGhostReadOperation();noRead(queued.current,"disabled queued read");check(!queued.ghostReadOperationActive,"cancelled queue stuck");
    for(boolean replace:new boolean[]{false,true}){
      InteractionHarness h=fresh();Client original=h.current;h.readSentMessageOnInteraction(new TdApi.Message());
      if(replace)h.current=new Client();else MoexConfig.ghostReadOnInteract=false;
      original.flush();check(original.views()==0,"read sent after token cancellation");
      check(original.sent.size()==2 && ((TdApi.SetOption)original.sent.get(1)).value instanceof TdApi.OptionValueEmpty,"cancelled token retained");
      check(!h.ghostReadOperationActive,"cancelled token stuck queue");
    }
    InteractionHarness serial=fresh();serial.readMessageOnInteraction(serial.current,-100,70);serial.readMessageOnInteraction(serial.current,42,80);
    check(serial.current.sent.size()==1,"permissions were interleaved");serial.current.flush();check(serial.current.views()==2,"second target dropped");
    InteractionHarness manual=fresh();MoexConfig.ghostReadOnInteract=false;manual.readMessageOnServer(-100,70);manual.current.flush();target(manual.current,-100,70);
    System.out.println("Read on interact: "+checks+" production-method checks passed");
  }
}
'''.replace("__METHODS__", methods)}, "InteractionHarness")

    def test_ui_persistence_and_event_wiring(self):
        config = CONFIG.read_text()
        self.assertIn('ghostReadOnInteract = instance().getBoolean(KEY_GHOST_READ_ON_INTERACT, false)', config)
        setter = block(CONFIG, "public void setGhostReadOnInteract (")
        self.assertIn("putBoolean(KEY_GHOST_READ_ON_INTERACT, enabled)", setter)
        ui = (JAVA / "moe/kirao/mgx/ui/SettingsMoexController.java").read_text()
        self.assertIn("setGhostReadOnInteract(adapter.toggleView(v))", ui)
        self.assertIn("setRadioEnabled(MoexConfig.ghostReadOnInteract, isUpdate)", ui)
        self.assertEqual(ui.count("ListItem.TYPE_RADIO_SETTING, R.id.btn_ghostReadOnInteract"), 1)
        for locale in ("values", "values-b+zh+Hans"):
            strings = ET.parse(ROOT / f"app/src/main/res/{locale}/moex_strings.xml").getroot()
            for name in ("GhostReadOnInteract", "GhostReadOnInteractInfo"):
                self.assertEqual(len(strings.findall(f"string[@name='{name}']")), 1)
        success = block(TDLIB, "private void updateMessageSendSucceeded (")
        self.assertIn("readSentMessageOnInteraction(update.message)", success)
        for signature in ("private void updateMessageSendFailed (", "private void updateNewMessage (", "void onMessageSendAcknowledged ("):
            self.assertNotIn("readSentMessageOnInteraction", block(TDLIB, signature))
        reactions = block(JAVA / "org/thunderdog/challegram/data/TGReactions.java", "public boolean toggleReaction (")
        self.assertEqual(reactions.count("tdlib.sendMessageInteraction("), 2)
        send = block(TDLIB, "public <T extends TdApi.Object> void send (TdApi.Function<T> function, ResultHandler<T> handler)")
        self.assertIn("sendMessageInteraction", send)


if __name__ == "__main__":
    unittest.main()
