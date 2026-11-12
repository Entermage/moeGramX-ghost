"""Run MessagesController's real attachment-send method with a controllable file worker.

The Android views and TDLib transport are scripted here. This exercises delayed
permission failure, draft/reply retention, empty preparation, scheduling and retry;
it is not an Android UI or Telegram server test.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'app/src/main/java/org/thunderdog/challegram/ui/MessagesController.java'
BASELINE = '800a794a6fa94b5d7b5a2b3b126eae8357804829'


def method(text, signature):
    start = text.index(signature)
    depth = 0
    for i in range(text.index('{', start), len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0: return text[start:i + 1]
    raise ValueError(signature)


HARNESS = r'''
import java.util.*;
public class AttachmentHarness {
  static class TdApi {
    static class FormattedText {}
    static class Object {}
    static class Message extends Object {}
    static class Messages extends Object {int totalCount;}
    static class MessageTopic {}
    static class InputMessageReplyTo {}
    static class Function<T> {}
    static class MessageSendOptions { java.lang.Object schedulingState; }
  }
  static class InlineResult<T> {
    static final int TYPE_AUDIO=1, TYPE_DOCUMENT=2;
    int getType(){return TYPE_DOCUMENT;} String getId(){return "file";}
  }
  static class InlineResultCommon extends InlineResult<Object> {
    int getType(){return TYPE_AUDIO;} Object getTag(){return new MediaBottomFilesController.MusicEntry();}
  }
  static class MediaBottomFilesController { static class MusicEntry {} }
  static class Input {
    String draft="caption"; TdApi.FormattedText getOutputText(boolean markdown){return new TdApi.FormattedText();}
  }
  static class Attached {
    ArrayList<InlineResult<?>> items=new ArrayList<>();
    ArrayList<InlineResult<?>> getCurrentItems(){return new ArrayList<>(items);}
  }
  static class ReplyInfo {TdApi.InputMessageReplyTo toInputMessageReply(){return new TdApi.InputMessageReplyTo();}}
  static class ThreadInfo {long getChatId(){return 1;} TdApi.MessageTopic getMessageTopicId(){return null;}}
  static class Manager { List<TdApi.Message> pending; void setSentMessages(List<TdApi.Message> m){pending=m;} }
  static class R { static class string { static int SlowFileAccess=1; } }
  static class Lang { static String getString(int i){return "slow";} }
  static class Toast { static int LENGTH_LONG=1; }
  static class MathUtils { static int clamp(int v,int lo,int hi){return Math.max(lo,Math.min(v,hi));} }
  static class RightId { static int SEND_AUDIO=1; }
  static class UI {
    static List<Runnable> timers=new ArrayList<>();
    static void post(Runnable r){r.run();} static void post(Runnable r,int delay){timers.add(r);}
    static void cancel(Runnable r){timers.remove(r);} static void showToast(String s,int len){}
    static void tick(){for(Runnable r:new ArrayList<>(timers))r.run(); timers.clear();}
  }
  interface Done { void runWithBool(boolean success); }
  interface Ready { void run(List<TdApi.Function<?>> functions); }
  final Input inputView=new Input(); final Object sendButton=new Object(); final Attached attachedFiles=new Attached();
  final Manager manager=new Manager(); ReplyInfo reply=new ReplyInfo();
  Object arguments=new Object(); boolean destroyed,isSendingText,slow,audioBlocked,networkOk=true,partial;
  int submitted; boolean scheduled; Ready pendingFiles;
  final Tdlib tdlib=new Tdlib(); interface Handler {void onResult(TdApi.Object result);}
  class Tdlib { Tdlib client(){return this;} Handler messageHandler(){return result->{};} void send(TdApi.Function<?> f,Handler h){submitted++;h.onResult(new TdApi.Message());} Tdlib ui(){return this;}void post(Runnable r){r.run();} }
  ThreadInfo messageThread;TdApi.MessageTopic getMessageTopicId(){return null;}
  void clearSentAttachmentDraft(long chat,TdApi.MessageTopic topic,ThreadInfo thread,TdApi.FormattedText text,TdApi.InputMessageReplyTo reply){}
  void setStackLocked(boolean locked){check(!locked,"attachment preparation locked navigation");}
  List<TdApi.Function<?>> musicResult=List.of(new TdApi.Function<>());
  boolean isEditingMessage(){return false;} void saveMessage(boolean markdown){}
  boolean hasAttachedFiles(){return true;} void sendText(boolean markdown,TdApi.MessageSendOptions options){}
  ReplyInfo getCurrentReplyId(){return reply;} long getChatId(){return 1;}
  Object getArguments(){return arguments;} boolean isDestroyed(){return destroyed;}
  void setIsSendingText(boolean b){isSendingText=b;}
  void setIsSendingText(boolean b,boolean lockStack){check(!lockStack,"preparation should not own navigation lock");isSendingText=b;}
  boolean showSlowModeRestriction(Object v,TdApi.MessageSendOptions o){return slow && (o==null || o.schedulingState==null);}
  boolean showRestriction(Object v,int right){return audioBlocked;}
  void clearInputAfterSend(boolean success,boolean allowReply,ReplyInfo oldReply,boolean link){
    if(!destroyed){manager.setSentMessages(null); if(success){inputView.draft="";attachedFiles.items.clear();if(allowReply&&reply==oldReply)reply=null;}setIsSendingText(false);}
  }
  List<TdApi.Function<?>> getSendMusicFunctions(Object v,List<MediaBottomFilesController.MusicEntry> music,boolean group,boolean allow,TdApi.FormattedText caption,TdApi.MessageSendOptions opts){
    return getSendMusicFunctions(v,music,group,allow,caption,opts,false);
  }
  List<TdApi.Function<?>> getSendMusicFunctions(Object v,List<MediaBottomFilesController.MusicEntry> music,boolean group,boolean allow,TdApi.FormattedText caption,TdApi.MessageSendOptions opts,boolean keepReply){
    if(showSlowModeRestriction(v,opts)||audioBlocked)return null;
    if(allow&&!keepReply)reply=null;
    return music.isEmpty()?Collections.emptyList():musicResult;
  }
  void sendFiles(Object v,List<String> files,boolean group,boolean allow,TdApi.FormattedText caption,TdApi.MessageSendOptions opts,Ready ready){sendFiles(v,files,group,allow,caption,opts,false,ready);}
  void sendFiles(Object v,List<String> files,boolean group,boolean allow,TdApi.FormattedText caption,TdApi.MessageSendOptions opts,boolean keepReply,Ready ready){
    if(showSlowModeRestriction(v,opts)){ready.run(null);return;}
    if(allow&&!keepReply)reply=null; pendingFiles=ready;
  }
  void executeSendMessageFunctions(List<TdApi.Function<?>> f,List<TdApi.Message> sent,boolean schedule,Done done){
    f.get(0); submitted+=f.size();scheduled=schedule;
    if(networkOk||partial)sent.add(new TdApi.Message());done.runWithBool(networkOk);
  }
  SEND_METHOD
  static void check(boolean b,String message){if(!b)throw new AssertionError(message);}
  void intact(){check(inputView.draft.equals("caption")&&!attachedFiles.items.isEmpty()&&reply!=null,"draft/reply lost");}
  static AttachmentHarness create(){AttachmentHarness h=new AttachmentHarness();h.attachedFiles.items.add(new InlineResult<>());return h;}
  public static void main(String[] args){
    AttachmentHarness h=create(); TdApi.MessageSendOptions o=new TdApi.MessageSendOptions();
    switch(args[0]){
      case "slow-mode": h.slow=true;h.send(o,true);h.intact();check(!h.isSendingText&&h.submitted==0&&h.pendingFiles==null,"slow mode locked/prepared");break;
      case "late-restriction": h.send(o,true);UI.tick();h.intact();check(h.isSendingText,"preparation unlocked");h.pendingFiles.run(null);h.intact();check(!h.isSendingText&&h.submitted==0,"restriction stuck/sent");break;
      case "empty": h.send(o,true);h.pendingFiles.run(Collections.emptyList());h.intact();check(!h.isSendingText&&h.submitted==0,"empty send");break;
      case "mixed-restriction": h.attachedFiles.items.add(new InlineResultCommon());h.send(o,true);h.pendingFiles.run(null);h.intact();check(h.submitted==0&&!h.isSendingText,"partial preparation sent");break;
      case "network-error": h.networkOk=false;h.send(o,true);h.pendingFiles.run(List.of(new TdApi.Function<>()));h.intact();check(!h.isSendingText,"error left send locked");break;
      case "scheduled": h.slow=true;o.schedulingState=new Object();h.send(o,true);h.pendingFiles.run(List.of(new TdApi.Function<>()));check(h.submitted==1&&h.scheduled&&!h.isSendingText&&h.inputView.draft.isEmpty(),"schedule failed");break;
      case "retry": h.send(o,true);UI.tick();h.pendingFiles.run(null);h.send(o,true);h.pendingFiles.run(List.of(new TdApi.Function<>()));check(h.submitted==1&&!h.isSendingText&&h.reply==null&&h.attachedFiles.items.isEmpty(),"retry failed");break;
      case "stale": h.send(o,true);h.arguments=new Object();h.pendingFiles.run(List.of(new TdApi.Function<>()));h.intact();check(h.submitted==1&&!h.isSendingText,"leaving page cancelled confirmed send");break;
      case "destroyed": h.send(o,true);h.destroyed=true;h.pendingFiles.run(List.of(new TdApi.Function<>()));check(h.submitted==1,"destroying page cancelled confirmed send");break;
      case "partial": h.networkOk=false;h.partial=true;h.send(o,true);h.pendingFiles.run(List.of(new TdApi.Function<>(),new TdApi.Function<>()));check(h.inputView.draft.isEmpty()&&!h.isSendingText,"accepted batch offered duplicate retry");break;
      default:throw new IllegalArgumentException(args[0]);
    }
    check(UI.timers.isEmpty(),"preparation timer leaked");System.out.println("ok "+args[0]);
  }
}
'''


class AttachmentSendTest(unittest.TestCase):
    def run_source(self, source, cases, expected=0):
        with tempfile.TemporaryDirectory(prefix='attachment-send-') as temp:
            base=Path(temp)
            java=base/'AttachmentHarness.java'
            java.write_text(HARNESS.replace('SEND_METHOD',method(source,'  private void send (TdApi.MessageSendOptions sendOptions, boolean applyMarkdown)')))
            result=subprocess.run(['javac','-encoding','UTF-8','-d',temp,str(java)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for case in cases:
                with self.subTest(case=case):
                    result=subprocess.run(['java','-ea','-cp',temp,'AttachmentHarness',case],capture_output=True,text=True,timeout=20)
                    if expected==0:self.assertEqual(result.returncode,0,result.stderr)
                    else:self.assertNotEqual(result.returncode,0,'old behavior unexpectedly passed '+case)

    def test_attachment_lifecycle(self):
        self.run_source((ROOT/SOURCE).read_text(),['slow-mode','late-restriction','empty','mixed-restriction','network-error','scheduled','retry','stale','destroyed','partial'])

    def test_old_behavior_fails(self):
        source=subprocess.check_output(['git','show',BASELINE+':'+SOURCE],cwd=ROOT,text=True)
        self.run_source(source,['slow-mode','late-restriction','empty','mixed-restriction','network-error','retry'],expected=1)


if __name__=='__main__': unittest.main()
