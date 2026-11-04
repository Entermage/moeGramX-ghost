"""Run extracted production methods with JVM doubles; not Android E2E."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

BASE = Path(__file__).resolve().parents[1] / 'app/src/main/java/org/thunderdog/challegram'


def method(path, signature):
    return block(BASE / path, signature)


def run_java(body):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'Backport.java').write_text('import java.util.*;\npublic class Backport {\n' + body + '\n}')
        compiled = subprocess.run(['javac', str(root / 'Backport.java')], capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        return subprocess.run(['java', '-cp', str(root), 'Backport'], capture_output=True, text=True)


CHECK = '''
static int checks;
static void check(boolean ok) { checks++; if (!ok) throw new AssertionError("check " + checks); }
@interface Nullable {} @interface NonNull {}
'''


def keyboard_source():
    sync = method('navigation/NavigationController.java', 'private void syncKeyboardState (')
    return CHECK + '''
static class Context { boolean shown; boolean isKeyboardVisible() { return shown; } }
static class UI { static Context getContext(Context c) { return c; } }
static class ViewController<T> {
  boolean keyboard; int changes;
  boolean getKeyboardState() { return keyboard; }
  void onKeyboardStateChanged(boolean v) { keyboard=v; changes++; }
}
Context context=new Context();
''' + sync + '''
public static void main(String[] args) {
  Backport n=new Backport(); ViewController<Object> c=new ViewController<>();
  c.keyboard=true; n.syncKeyboardState(c); check(!c.keyboard && c.changes==1);
  n.syncKeyboardState(c); check(c.changes==1);
  n.context.shown=true; c.keyboard=true; n.syncKeyboardState(c); check(c.keyboard && c.changes==1);
  c.keyboard=false; n.syncKeyboardState(c); check(!c.keyboard && c.changes==1);
}
'''


def download_source():
    production = method('telegram/TdlibFilesManager.java', 'public boolean canAutomaticallyDownload (')
    return CHECK + '''
static class TdApi {
 static class File { int id=1; long size=20; Remote remote=new Remote(); }
 static class Remote { boolean isUploadingActive; }
 static class ChatType { int getConstructor() { return 99; } }
 static class ChatTypePrivate extends ChatType { static final int CONSTRUCTOR=1; int getConstructor(){return CONSTRUCTOR;} }
 static class ChatTypeSecret extends ChatType { static final int CONSTRUCTOR=2; int getConstructor(){return CONSTRUCTOR;} }
 static class ChatTypeBasicGroup extends ChatType { static final int CONSTRUCTOR=3; int getConstructor(){return CONSTRUCTOR;} }
 static class ChatTypeSupergroup extends ChatType { static final int CONSTRUCTOR=4; boolean channel; ChatTypeSupergroup(boolean c){channel=c;} int getConstructor(){return CONSTRUCTOR;} }
}
static class TD { static boolean isSupergroup(TdApi.ChatType t) { return !((TdApi.ChatTypeSupergroup)t).channel; } }
static class WatchDog { static final int CONNECTION_TYPE_WIFI=1, CONNECTION_TYPE_ROAMING=2, CONNECTION_TYPE_MOBILE=3; int type=1; int getConnectionType(){return type;} }
static class Tdlib { WatchDog dog=new WatchDog(); Tdlib context(){return this;} WatchDog watchDog(){return dog;} }
Tdlib tdlib=new Tdlib();
boolean saving; int sizeValidation;
static final int VALIDATE_FILE_SIZE_OK=0, DOWNLOAD_DEFAULTS=1, DOWNLOAD_PRIVATE_SHIFT=0;
int downloadInPrivateChats,downloadInGroupChats=2,downloadInChannelChats=4;
int downloadLimitOverWiFi=100,downloadLimitOverRoaming=30,downloadLimitOverMobile=50;
int downloadWiFiExclude,downloadRoamingExclude,downloadMobileExclude;
Set<Integer> manuallyCancelledFiles=new HashSet<>();
boolean isDataSaverActive(){return saving;} int validateDownloadFileSize(TdApi.File f){return sizeValidation;}
long getDownloadLimit(int n){return n;}
''' + production + '''
public static void main(String[] args) {
 Backport b=new Backport(); TdApi.File f=new TdApi.File();
 check(!b.canAutomaticallyDownload(f,1,null));
 b.downloadInPrivateChats=8; check(b.canAutomaticallyDownload(f,8,null)); check(!b.canAutomaticallyDownload(f,1,null));
 for(int network=1;network<=3;network++) {
  b.tdlib.dog.type=network;
  check(b.canAutomaticallyDownload(f,8,null));
  check(b.canAutomaticallyDownload(f,8,new TdApi.ChatTypePrivate()));
  check(b.canAutomaticallyDownload(f,8,new TdApi.ChatTypeSecret()));
  check(b.canAutomaticallyDownload(f,2,new TdApi.ChatTypeBasicGroup()));
  check(b.canAutomaticallyDownload(f,2,new TdApi.ChatTypeSupergroup(false)));
  check(b.canAutomaticallyDownload(f,4,new TdApi.ChatTypeSupergroup(true)));
  check(!b.canAutomaticallyDownload(f,8,new TdApi.ChatType()));
  f.size=101; check(!b.canAutomaticallyDownload(f,8,null)); f.size=20;
 }
 b.saving=true; check(!b.canAutomaticallyDownload(f,8,null)); b.saving=false;
 f.remote.isUploadingActive=true; check(!b.canAutomaticallyDownload(f,8,null)); f.remote.isUploadingActive=false;
 b.manuallyCancelledFiles.add(1); check(!b.canAutomaticallyDownload(f,8,null)); b.manuallyCancelledFiles.clear();
 b.sizeValidation=1; check(!b.canAutomaticallyDownload(f,8,null)); b.sizeValidation=0;
 b.tdlib.dog.type=1; b.downloadWiFiExclude=8; check(!b.canAutomaticallyDownload(f,8,null));
 b.tdlib.dog.type=2; b.downloadRoamingExclude=8; check(!b.canAutomaticallyDownload(f,8,null));
 b.tdlib.dog.type=3; b.downloadMobileExclude=8; check(!b.canAutomaticallyDownload(f,8,null));
 System.out.println("download policy checks="+checks);
}
'''


def poll_source():
    production = method('data/TGMessageService.java', 'private void setPollOptionAddDeleteTextCreator (')
    return CHECK + '''
static class TdApi {
 static class FormattedText {}
 static class Message { long chatId=1; boolean isOutgoing; Object content; }
 static class Poll { String question="poll"; }
 static class MessagePoll { Poll poll=new Poll(); }
}
static class Td { static boolean isPoll(Object c){return c instanceof TdApi.MessagePoll;} }
static class R { static class string { static final int ActionDeletedPollOutOption=1,ActionAddedPollOutOption=2,ActionDeletedPollOption=3,ActionAddedPollOption=4,ActionDeletedPollOutOptionMsg=5,ActionAddedPollOutOptionMsg=6,ActionDeletedPollOptionMsg=7,ActionAddedPollOptionMsg=8; } }
static class FormattedTextArgument { FormattedTextArgument(Object o){} }
static class SenderArgument { SenderArgument(Object o){} }
static class MessageArgument { MessageArgument(Object o,Object q){} }
TdApi.Message msg=new TdApi.Message(), target=new TdApi.Message(); Object sender; int textId; boolean accepted;
int getText(int id,Object... args){return id;}
void setTextCreator(java.util.function.Supplier<Integer> f){textId=f.get();}
void setDisplayMessage(long c,long id,java.util.function.Predicate<TdApi.Message> p){accepted=p.test(target);}
''' + production + '''
public static void main(String[] args) {
 Backport b=new Backport();
 for(boolean out:new boolean[]{false,true}) for(boolean del:new boolean[]{false,true}) {
  b.msg.isOutgoing=out; b.target.content="not a poll";
  b.setPollOptionAddDeleteTextCreator(del,new TdApi.FormattedText(),7);
  check(!b.accepted && b.textId<=4);
  b.target.content=new TdApi.MessagePoll();
  b.setPollOptionAddDeleteTextCreator(del,new TdApi.FormattedText(),7);
  check(b.accepted && b.textId>=5);
 }
}
'''


def paint_source():
    production = method('mediaview/MediaViewController.java', 'private void hidePaintEditor ()')
    return CHECK + '''
static class Paint { boolean visible=true,paused; float x=2,y=2; void setEditorVisible(boolean v){visible=v;} void pause(){paused=true;} void setScaleX(float v){x=v;} void setScaleY(float v){y=v;} }
static class Item { boolean changed=true; Object getPaintState(){return null;} boolean setPaintState(Object s,boolean b){return changed;} }
static class Media { int invalidations; Media getBaseReceiver(){return this;} void invalidate(){invalidations++;} }
Paint paintView; Item paintingItem; Media mediaView; int hints;
void showDefaultBrushHint(){hints++;}
''' + production + '''
public static void main(String[] args) {
 for(int mask=0;mask<8;mask++) {
  Backport b=new Backport();
  if((mask&1)!=0)b.paintView=new Paint();
  if((mask&2)!=0)b.paintingItem=new Item();
  if((mask&4)!=0)b.mediaView=new Media();
  b.hidePaintEditor(); check(b.hints==1);
  if(b.paintView!=null)check(!b.paintView.visible && b.paintView.paused && b.paintView.x==1 && b.paintView.y==1);
  if(b.mediaView!=null)check(b.mediaView.invalidations==((mask&2)!=0?1:0));
 }
}
'''


def location_source():
    production = method('telegram/LiveLocationManager.java', 'if (!isTitle && messages.size() == 2)')
    return CHECK + '''
static class TdApi {
 static class Location { double latitude,longitude; Location(double a,double b){latitude=a;longitude=b;} }
 static class LiveLocation { Location location; LiveLocation(Location l){location=l;} }
 static class MessageLiveLocation { LiveLocation location; MessageLiveLocation(Location l){location=new LiveLocation(l);} }
 static class MessageLocation { Location location; }
 static class Message { boolean isOutgoing; Object content; Message(boolean out, double x,double y){isOutgoing=out;content=new MessageLiveLocation(new Location(x,y));} }
}
static class U { static float distanceBetween(double a,double b,double c,double d){check(c==7 && d==8);return (float)(a+b+c+d);} }
static class Lang { static String lowercase(String s){return s;} static String shortDistanceToPerson(float f){return Float.toString(f);} }
static String distance(boolean isTitle,ArrayList<TdApi.Message> messages,TdApi.Message outputMessage,TdApi.Location myLocation) {
''' + production + '''
 return null;
}
public static void main(String[] args) {
 TdApi.Message mine=new TdApi.Message(true,1,2), peer=new TdApi.Message(false,7,8);
 for(boolean reversed:new boolean[]{false,true}) {
  ArrayList<TdApi.Message> messages=new ArrayList<>(reversed?List.of(peer,mine):List.of(mine,peer));
  check(distance(false,messages,mine,null).equals("18.0"));
  check(distance(false,messages,mine,new TdApi.Location(3,4)).equals("22.0"));
  check(distance(true,messages,mine,null)==null);
 }
}
'''


class UpstreamBackportsTest(unittest.TestCase):
    def assert_runs(self, source):
        result = run_java(source)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_keyboard_reattach_reconciles_only_stale_visible_state(self):
        self.assert_runs(keyboard_source())
        for signature in ['public void addChildWrapper (ViewController<?> controller)',
                          'public void addChildWrapper (ViewController<?> controller, int index)']:
            body = method('navigation/NavigationController.java', signature)
            self.assertLess(body.index('syncKeyboardState(controller);'), body.index('controller.onPrepareToShow();'))

    def test_keyboard_old_behavior_is_rejected(self):
        old = keyboard_source().replace('controller.onKeyboardStateChanged(false);', ';')
        self.assertNotEqual(0, run_java(old).returncode)

    def test_download_preferences_and_all_existing_limits(self):
        self.assert_runs(download_source())

    def test_old_no_chat_download_defaults_are_rejected(self):
        source = download_source()
        source = source.replace('automaticDownloadTypes = downloadInPrivateChats;', 'automaticDownloadTypes = (DOWNLOAD_DEFAULTS >> DOWNLOAD_PRIVATE_SHIFT) & 0xff;', 1)
        self.assertNotEqual(0, run_java(source).returncode)

    def test_poll_service_message_fallback_and_valid_poll(self):
        self.assert_runs(poll_source())

    def test_old_poll_guard_is_rejected(self):
        self.assertNotEqual(0, run_java(poll_source().replace('!Td.isPoll(message.content)', 'Td.isPoll(message.content)')).returncode)

    def test_paint_exit_with_partial_teardown(self):
        self.assert_runs(paint_source())

    def test_old_paint_teardown_is_rejected(self):
        self.assertNotEqual(0, run_java(paint_source().replace('if (paintView != null)', 'if (true)')).returncode)

    def test_live_location_distance_accepts_current_tdlib_content(self):
        self.assert_runs(location_source())

    def test_old_live_location_cast_is_rejected(self):
        old = location_source().replace('((TdApi.MessageLiveLocation) outputMessage.content).location.location', '((TdApi.MessageLocation) outputMessage.content).location').replace('((TdApi.MessageLiveLocation) msg.content).location.location', '((TdApi.MessageLocation) msg.content).location')
        self.assertNotEqual(0, run_java(old).returncode)

    def test_oem_fully_drawn_failure_does_not_break_ready_state(self):
        production = method('BaseActivity.java', 'public void markActivityReady ()')
        self.assert_runs(CHECK + '''
boolean activityReady; int reports;
static class Log { static int errors; static void i(String s,Throwable t){errors++;} }
void reportFullyDrawn(){reports++;throw new SecurityException("OEM");}
''' + production + '''
public static void main(String[] a){Backport b=new Backport();b.markActivityReady();b.markActivityReady();check(b.activityReady && b.reports==1 && Log.errors==1);}
''')

    def test_recycled_media_logging_accepts_missing_media(self):
        source = (BASE / 'mediaview/MediaCellView.java').read_text()
        start = source.index('Log.i("videoCell #%d:')
        statement = source[start:source.index(');', start)+2]
        self.assert_runs(CHECK + '''
static class Log { static void i(String s,Object... args){} }
static class Media { Object getCropState(){return null;} boolean isVideoRenderRotated(boolean b){return false;} }
public static void main(String[] args){int i=0,imageWidth=1,imageHeight=1,imageWidthOriginal=1,imageHeightOriginal=1; Media media=null;
''' + statement + '\ncheck(true);}\n')


if __name__ == '__main__':
    unittest.main()
