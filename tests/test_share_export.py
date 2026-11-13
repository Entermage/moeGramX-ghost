"""Execute ShareController's production export eligibility against real TdApi.

The old author-id gate must fail hidden-origin cases; normal origins and file,
MIME, sending-state and secret-media restrictions must remain unchanged.
Android chooser rendering and cross-UID URI reads require device validation.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

from test_media_viewer_share import ANNOTATIONS, BASELINE, TDAPI, method

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'app/src/main/java/org/thunderdog/challegram/ui/ShareController.java'

HARNESS = r'''
import java.util.*;
import org.drinkless.tdlib.TdApi;
public class ExportHarness {
 static final int MODE_MESSAGES=0,MODE_TEXT=1,MODE_GAME=2,MODE_FILES=3,MODE_CONTACT=4,MODE_STICKER=5,MODE_CUSTOM=6,MODE_CUSTOM_CONTENT=7,MODE_TELEGRAM_FILES=8;
 static final int EXPORT_NONE=0,EXPORT_AVAILABLE=1,EXPORT_DISABLED=2;
 static final boolean ALLOW_SHARED_PRIVATE=true;
 static class MediaItem { String getShareMimeType(){return "image/jpeg";} }
 static class Args {String exportText;TdApi.Message[] messages;MediaItem[] telegramFiles;}
 static class StringUtils {static boolean isEmpty(String s){return s==null||s.isEmpty();}}
 static class ChatId {static boolean isUserChat(long id){return id>0;}}
 static class Tdlib {boolean isSelfChat(long id){return id==100;}}
 static class Td {
  static long getMessageAuthorId(TdApi.Message m){
   if(m.forwardInfo!=null){TdApi.MessageOrigin o=m.forwardInfo.origin;
    if(o instanceof TdApi.MessageOriginHiddenUser)return 0;
    if(o instanceof TdApi.MessageOriginUser)return ((TdApi.MessageOriginUser)o).senderUserId;
    if(o instanceof TdApi.MessageOriginChat)return ((TdApi.MessageOriginChat)o).senderChatId;
    if(o instanceof TdApi.MessageOriginChannel)return ((TdApi.MessageOriginChannel)o).chatId;
   }
   return ((TdApi.MessageSenderUser)m.senderId).userId;
  }
 }
 static class TD {
  static boolean isFileLoadedAndExists(TdApi.File f){return f.local!=null&&f.local.isDownloadingCompleted&&!f.local.path.isEmpty();}
  static String getMimeType(TdApi.LinkPreview p){return null;}
 }
 static class U {static String getExtension(String n){return "";}}
 static class TGMimeType {static String mimeTypeForExtension(String e){return null;}}
 int mode=MODE_MESSAGES;Args args=new Args();Tdlib tdlib=new Tdlib();List<TdApi.File> awaitingFiles;
 static final Map<TdApi.Message,TdApi.File> FILES=new IdentityHashMap<>();
 Args getArgumentsStrict(){return args;}
 TdApi.File getFile(TdApi.Message m){return FILES.get(m);}
 PRODUCTION_METHODS
 static void check(boolean yes,String why){if(!yes)throw new AssertionError(why);}
 static TdApi.Message photo(String origin){
  TdApi.Message m=new TdApi.Message();m.chatId=100;m.senderId=new TdApi.MessageSenderUser(777000);m.canBeSaved=true;
  m.content=new TdApi.MessagePhoto();
  if(!origin.equals("none")){m.forwardInfo=new TdApi.MessageForwardInfo();switch(origin){
   case "hidden":m.forwardInfo.origin=new TdApi.MessageOriginHiddenUser("Synthetic sender");break;
   case "user":m.forwardInfo.origin=new TdApi.MessageOriginUser(123);break;
   case "chat":m.forwardInfo.origin=new TdApi.MessageOriginChat();((TdApi.MessageOriginChat)m.forwardInfo.origin).senderChatId=-77;break;
   case "channel":m.forwardInfo.origin=new TdApi.MessageOriginChannel();((TdApi.MessageOriginChannel)m.forwardInfo.origin).chatId=-88;break;
   default:throw new IllegalArgumentException(origin);
  }}
  TdApi.File f=new TdApi.File();f.local=new TdApi.LocalFile();f.local.path="fixture.jpg";f.local.isDownloadingCompleted=true;FILES.put(m,f);return m;
 }
 public static void main(String[] argv){
  String c=argv[0];ExportHarness h=new ExportHarness();TdApi.Message m=photo(c.startsWith("known-")?c.substring(6):"hidden");h.args.messages=new TdApi.Message[]{m};int expected=EXPORT_AVAILABLE;
  switch(c){
   case "hidden-loaded":case "known-none":case "known-user":case "known-chat":case "known-channel":break;
   case "hidden-awaiting":FILES.get(m).local.isDownloadingCompleted=false;expected=EXPORT_DISABLED;break;
   case "hidden-empty-path":FILES.get(m).local.path="";expected=EXPORT_DISABLED;break;
   case "hidden-first":h.args.messages=new TdApi.Message[]{m,photo("user")};break;
   case "hidden-last":h.args.messages=new TdApi.Message[]{photo("user"),m};break;
   case "all-hidden":h.args.messages=new TdApi.Message[]{m,photo("hidden")};break;
   case "protected-hidden":m.canBeSaved=false;expected=EXPORT_NONE;break;
   case "protected-known":m=photo("user");m.canBeSaved=false;h.args.messages=new TdApi.Message[]{m};expected=EXPORT_NONE;break;
   case "protected-album":{TdApi.Message other=photo("user");other.canBeSaved=false;h.args.messages=new TdApi.Message[]{m,other};expected=EXPORT_NONE;break;}
   case "pending":m.sendingState=new TdApi.MessageSendingStatePending();expected=EXPORT_NONE;break;
   case "failed":m.sendingState=new TdApi.MessageSendingStateFailed();expected=EXPORT_NONE;break;
   case "secret-photo":((TdApi.MessagePhoto)m.content).isSecret=true;expected=EXPORT_NONE;break;
   case "missing-file":FILES.remove(m);expected=EXPORT_NONE;break;
   case "mixed-mime":{TdApi.Message video=photo("user");TdApi.MessageVideo v=new TdApi.MessageVideo();v.video=new TdApi.Video();v.video.mimeType="video/mp4";video.content=v;h.args.messages=new TdApi.Message[]{m,video};expected=EXPORT_NONE;break;}
   case "empty":h.args.messages=new TdApi.Message[0];expected=EXPORT_NONE;break;
   case "hidden-document":{TdApi.MessageDocument d=new TdApi.MessageDocument();d.document=new TdApi.Document();d.document.fileName="synthetic.pdf";d.document.mimeType="application/pdf";m.content=d;break;}
   default:throw new IllegalArgumentException(c);
  }
  int actual=h.getExportContentState();check(actual==expected,c+": expected "+expected+", got "+actual);
  if(expected==EXPORT_DISABLED){check(h.awaitingFiles!=null&&h.awaitingFiles.size()==1&&h.awaitingFiles.get(0)==FILES.get(m),"Download queue incorrect");FILES.get(m).local.path="fixture.jpg";FILES.get(m).local.isDownloadingCompleted=true;check(h.getExportContentState()==EXPORT_AVAILABLE,"Downloaded file still unavailable");check(h.awaitingFiles==null,"Completed download queue retained");}
  System.out.println("ok "+c);
 }
}
'''

class ShareExportTest(unittest.TestCase):
    CASES = ('hidden-loaded', 'known-none', 'known-user', 'known-chat', 'known-channel',
             'hidden-awaiting', 'hidden-empty-path', 'hidden-first', 'hidden-last',
             'all-hidden', 'pending', 'failed', 'secret-photo', 'missing-file',
             'mixed-mime', 'empty', 'hidden-document', 'protected-hidden',
             'protected-known', 'protected-album')
    BROKEN = {'hidden-loaded', 'hidden-awaiting', 'hidden-empty-path',
              'hidden-first', 'hidden-last', 'all-hidden', 'hidden-document'}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='share-export-')
        cls.base = Path(cls.tmp.name)
        src = cls.base / 'tdapi-src'
        for name, text in ANNOTATIONS.items():
            p=src/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        p=src/'org/drinkless/tdlib/TdApi.java';p.parent.mkdir(parents=True);shutil.copy(TDAPI,p)
        cls.tdapi=cls.base/'tdapi'
        subprocess.run(['javac','-nowarn','-encoding','UTF-8','-d',str(cls.tdapi),
                        *map(str,src.rglob('*.java'))],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def compile(self, source, name):
        out=self.base/name;out.mkdir()
        methods='\n'.join(method(source,s) for s in (
            '  private int getExportContentState ()',
            '  private String getExportMimeType (TdApi.Message message)',
            '  private static boolean canExportStaticContent (TdApi.Message msg)'))
        java=out/'ExportHarness.java';java.write_text(HARNESS.replace('PRODUCTION_METHODS',methods))
        r=subprocess.run(['javac','-encoding','UTF-8','-cp',str(self.tdapi),'-d',str(out),str(java)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        return out

    def run_cases(self,classes,baseline=False):
        for case in self.CASES:
            with self.subTest(case=case):
                r=subprocess.run(['java','-ea','-cp',os.pathsep.join(map(str,[classes,self.tdapi])),
                                  'ExportHarness',case],capture_output=True,text=True,timeout=30)
                if baseline and (case in self.BROKEN or case == 'protected-known'):
                    self.assertNotEqual(r.returncode,0,r.stdout)
                    self.assertIn('got 1' if case == 'protected-known' else 'got 0',r.stderr)
                else:
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertIn('ok '+case,r.stdout)

    def test_production_export(self):
        self.run_cases(self.compile((ROOT/SOURCE).read_text(),'current'))

    def test_old_author_gate_negative_control(self):
        old=subprocess.run(['git','-C',str(ROOT),'show',f'{BASELINE}:{SOURCE}'],check=True,capture_output=True,text=True).stdout
        self.run_cases(self.compile(old,'baseline'),baseline=True)

if __name__=='__main__':unittest.main()
