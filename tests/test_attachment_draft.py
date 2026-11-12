"""Exercise production sent-draft cleanup and send-lock ownership with JVM doubles.
No server or Android UI is simulated by these tests.
"""
import unittest
from test_upstream_backports import CHECK, method, run_java


def cleanup_source():
    return CHECK + r'''
static class TdApi {
 record FormattedText(String text) {} record InputMessageReplyTo(long id) {}
 static class MessageTopic {} static class MessageTopicForum extends MessageTopic {long forumTopicId=12;}
 static class DraftMessage {FormattedText text;InputMessageReplyTo replyTo;DraftMessage(String t,long r){text=new FormattedText(t);replyTo=new InputMessageReplyTo(r);}}
 static class Chat {DraftMessage draftMessage;}static class ForumTopic {DraftMessage draftMessage;}static class MessageThreadInfo {DraftMessage draftMessage;}
 static class Function<T> {} static class Ok {}
 static class GetChat extends Function<Chat> {long chatId;GetChat(long c){chatId=c;}}
 static class GetMessageThread extends Function<MessageThreadInfo> {long chatId,messageId;GetMessageThread(long c,long m){chatId=c;messageId=m;}}
 static class GetForumTopic extends Function<ForumTopic> {long chatId,topicId;GetForumTopic(long c,long t){chatId=c;topicId=t;}}
 static class SetChatDraftMessage extends Function<Ok> {long chatId;MessageTopic topicId;DraftMessage draft;SetChatDraftMessage(long c,MessageTopic t,DraftMessage d){chatId=c;topicId=t;draft=d;}}
}
interface RunnableData<T>{void runWithData(T value);}interface Handler<T>{void done(T value,Object error);}
static class ThreadInfo {TdApi.DraftMessage draft;TdApi.DraftMessage getDraft(){return draft;}long getOldestMessageId(){return 42;}void setDraft(TdApi.DraftMessage d){draft=d;}}
static class UI {static void showError(Object error){}}
static class Td {static boolean equalsTo(Object a,Object b){return Objects.equals(a,b);}static TdApi.FormattedText textContent(TdApi.DraftMessage d){return d.text;}}
static class Tdlib {
 TdApi.DraftMessage current;boolean error;List<TdApi.Function<?>> queries=new ArrayList<>();List<TdApi.SetChatDraftMessage> clears=new ArrayList<>();
 Handler<TdApi.Ok> typedOkHandler(){return (ok,error)->{};}
 Tdlib ui(){return this;}void post(Runnable r){r.run();}
 @SuppressWarnings("unchecked") <T> void send(TdApi.Function<T> function,Handler<T> callback){
  if(function instanceof TdApi.SetChatDraftMessage){clears.add((TdApi.SetChatDraftMessage)function);callback.done((T)new TdApi.Ok(),null);return;}
  queries.add(function);if(error){callback.done(null,new Object());return;}
  if(function instanceof TdApi.GetChat){TdApi.Chat c=new TdApi.Chat();c.draftMessage=current;callback.done((T)c,null);}
  else if(function instanceof TdApi.GetMessageThread){TdApi.MessageThreadInfo t=new TdApi.MessageThreadInfo();t.draftMessage=current;callback.done((T)t,null);}
  else {TdApi.ForumTopic t=new TdApi.ForumTopic();t.draftMessage=current;callback.done((T)t,null);}
 }
}
Tdlib tdlib=new Tdlib();
''' + method('ui/MessagesController.java','private void clearSentAttachmentDraft (') + r'''
public static void main(String[] args){
 Backport b=new Backport();TdApi.FormattedText text=new TdApi.FormattedText("caption");TdApi.InputMessageReplyTo reply=new TdApi.InputMessageReplyTo(4);
 b.tdlib.current=new TdApi.DraftMessage("caption",4);b.clearSentAttachmentDraft(7,null,null,text,reply);
 check(b.tdlib.clears.size()==1&&b.tdlib.clears.get(0).chatId==7&&b.tdlib.clears.get(0).draft==null);
 b.tdlib.current=new TdApi.DraftMessage("new draft",4);b.clearSentAttachmentDraft(7,null,null,text,reply);check(b.tdlib.clears.size()==1);
 b.tdlib.current=new TdApi.DraftMessage("caption",8);b.clearSentAttachmentDraft(7,null,null,text,reply);check(b.tdlib.clears.size()==1);
 b.tdlib.error=true;b.clearSentAttachmentDraft(7,null,null,text,reply);check(b.tdlib.clears.size()==1);b.tdlib.error=false;
 b.tdlib.current=new TdApi.DraftMessage("caption",4);TdApi.MessageTopicForum topic=new TdApi.MessageTopicForum();b.clearSentAttachmentDraft(9,topic,null,text,reply);
 check(b.tdlib.clears.size()==2&&b.tdlib.clears.get(1).topicId==topic&&b.tdlib.clears.get(1).chatId==9);
 TdApi.GetForumTopic query=(TdApi.GetForumTopic)b.tdlib.queries.get(b.tdlib.queries.size()-1);check(query.chatId==9&&query.topicId==12);
 ThreadInfo thread=new ThreadInfo();thread.draft=b.tdlib.current;int queries=b.tdlib.queries.size();b.clearSentAttachmentDraft(11,topic,thread,text,reply);check(b.tdlib.queries.size()==queries+1&&b.tdlib.clears.size()==3&&thread.draft==null);
 TdApi.GetMessageThread tq=(TdApi.GetMessageThread)b.tdlib.queries.get(queries);check(tq.chatId==11&&tq.messageId==42);
 thread.draft=new TdApi.DraftMessage("caption",4);b.tdlib.current=new TdApi.DraftMessage("new thread draft",4);b.clearSentAttachmentDraft(11,topic,thread,text,reply);check(b.tdlib.clears.size()==3&&thread.draft!=null);
 b.tdlib.current=new TdApi.DraftMessage("caption",4);b.tdlib.current.replyTo=null;b.clearSentAttachmentDraft(7,null,null,text,null);check(b.tdlib.clears.size()==4);
 b.clearSentAttachmentDraft(7,null,null,text,reply);check(b.tdlib.clears.size()==4);
 b.tdlib.current.text=null;b.clearSentAttachmentDraft(7,null,null,null,null);check(b.tdlib.clears.size()==5);
 b.clearSentAttachmentDraft(7,null,null,text,null);check(b.tdlib.clears.size()==5);
}
'''


def lock_source():
    return CHECK + '''
boolean isSendingText,sendOwnsStackLock,locked;int lockWrites;
static class Input{boolean blocked;void setInputBlocked(boolean b){blocked=b;}}Input inputView=new Input();
boolean isStackLocked(){return locked;}void setStackLocked(boolean b){locked=b;lockWrites++;}
''' + method('ui/MessagesController.java','private void setIsSendingText (boolean isSendingText)') + method('ui/MessagesController.java','private void setIsSendingText (boolean isSendingText, boolean lockStack)') + '''
public static void main(String[] args){
 Backport b=new Backport();b.setIsSendingText(true,false);check(b.isSendingText&&b.inputView.blocked&&!b.locked&&b.lockWrites==0);
 b.locked=true; // Another controller starts sending while this one prepares attachments.
 b.setIsSendingText(false);check(b.locked&&!b.isSendingText&&!b.inputView.blocked&&b.lockWrites==0);
 b.setIsSendingText(true);b.setIsSendingText(false);check(b.locked&&b.lockWrites==0); // A pre-existing lock is not ours.
 b.locked=false;b.setIsSendingText(true);check(b.locked&&b.sendOwnsStackLock);b.setIsSendingText(false);check(!b.locked&&!b.sendOwnsStackLock&&b.lockWrites==2);
}
'''


class AttachmentDraftTest(unittest.TestCase):
    def test_only_matching_draft_is_cleared_in_original_context(self):
        result=run_java(cleanup_source());self.assertEqual(result.returncode,0,result.stderr)

    def test_changed_draft_protection_negative_control(self):
        result=run_java(cleanup_source().replace('Td.equalsTo(Td.textContent(draft), text)', 'true'))
        self.assertNotEqual(result.returncode,0)

    def test_other_controllers_lock_is_preserved(self):
        result=run_java(lock_source());self.assertEqual(result.returncode,0,result.stderr)

    def test_unowned_unlock_negative_control(self):
        result=run_java(lock_source().replace('!isSendingText && sendOwnsStackLock', '!isSendingText'))
        self.assertNotEqual(result.returncode,0)


if __name__=='__main__': unittest.main()
