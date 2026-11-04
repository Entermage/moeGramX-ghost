"""Exercise production media-origin methods with a small translated view hierarchy.

The negative control is the old pane-local calculation. Android animation remains
an emulator/device check; this harness checks coordinates and cached rectangle reuse.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java/org/thunderdog/challegram"
MC = JAVA / "ui/MessagesController.java"
SHARED = JAVA / "ui/SharedBaseController.java"
THUMB = JAVA / "mediaview/MediaViewThumbLocation.java"
WRAPPER = JAVA / "data/MediaWrapper.java"


def harness(old=False):
    chat = block(MC, "public MediaViewThumbLocation getTargetLocation (")
    shared = block(SHARED, "public MediaViewThumbLocation getTargetLocation (")
    if old:
        start = chat.index("            // The media viewer covers")
        end = chat.index("            return location;", start) + len("            return location;")
        chat = chat[:start] + """            int offset = (int) messagesView.getTranslationY();
            return msg.getMediaThumbLocation(item.getSourceMessageId(), view, view.getTop() - getTopOffset(), messagesView.getBottom() - view.getBottom(), view.getTop() + HeaderView.getSize(true) + offset);""" + chat[end:]
        shared = shared.replace("location.set(0, 0, view.getMeasuredWidth(), view.getMeasuredHeight());", "location.set(view.getLeft(), view.getTop() + recyclerView.getTop() + HeaderView.getSize(true), view.getRight(), view.getTop() + recyclerView.getTop() + HeaderView.getSize(true) + view.getMeasuredHeight());")
        shared = shared.replace("location.offsetToWindow(view);", "")
    methods = "\n".join(block(THUMB, s) for s in (
        "public void set (", "public void setClip (", "public void offsetToWindow (",
    ))
    source = TEMPLATE.replace("/* THUMB */", methods).replace("/* CHAT */", chat).replace("/* SHARED */", shared)
    return source.replace("/* WRAPPER */", block(WRAPPER, "public MediaViewThumbLocation getMediaThumbLocation ("))


TEMPLATE = r"""
import java.util.*;
public class MediaOriginHarness {
  static class View {
    View parent; int left, top, width=500, height=600, scrollX, scrollY; float translationX, translationY;
    View(View p, int x, int y) { parent=p; left=x; top=y; }
    int getLeft(){return left;} int getTop(){return top;}
    int getRight(){return left+width;} int getBottom(){return top+height;}
    int getMeasuredWidth(){return width;} int getMeasuredHeight(){return height;}
    float getTranslationY(){return translationY;}
    void getLocationInWindow(int[] out) {
      float x=0,y=0; for(View v=this;v!=null;v=v.parent){
        x+=v.left+v.translationX; y+=v.top+v.translationY;
        if(v.parent!=null){x-=v.parent.scrollX;y-=v.parent.scrollY;}
      } out[0]=Math.round(x);out[1]=Math.round(y);
    }
  }
  static class RecyclerView extends View {
    View row; RecyclerView(View p,int x,int y){super(p,x,y);}
    static class ViewHolder {int getItemViewType(){return 1;}}
    ViewHolder getChildViewHolder(View v){return new MessagesHolder();}
    LayoutManager getLayoutManager(){return new LayoutManager(this);}
  }
  static class MessagesHolder extends RecyclerView.ViewHolder {static boolean isMessageType(int type){return type==1;}}
  static class LayoutManager {RecyclerView recycler;LayoutManager(RecyclerView r){recycler=r;}View findViewByPosition(int i){return recycler.row;}}
  static class MediaItem {long getSourceMessageId(){return 123;}}
  interface MediaViewDelegate {MediaViewThumbLocation getTargetLocation(int i,MediaItem item);}
  static class MediaViewThumbLocation {
    int left,top,right,bottom,clipLeft,clipTop,clipRight,clipBottom;float topLeftRadius,topRightRadius,bottomRightRadius,bottomLeftRadius;boolean noBounce;
    void setNoBounce(){noBounce=true;}
    void setRoundings(float a,float b,float c,float d){topLeftRadius=a;topRightRadius=b;bottomRightRadius=c;bottomLeftRadius=d;}
    /* THUMB */
  }
  static class Screen {static int dp(float n){return Math.round(n);}}
  static class Theme {static float getBubbleMergeRadius(){return 12;}static float getBubbleDefaultRadius(){return 18;}}
  static class HeaderView {static int getSize(boolean b){return 220;}}
  static class MediaTabsAdapter {static final int POSITION_MESSAGES=0;}
  static class ListItem {static final int TYPE_FAKE_PAGER_TOPVIEW=1;}
  static class SettingHolder {static int measureHeightForType(int t){return 160;}}
  static class MediaWrapper {
    static final int ROUND_TOP_LEFT=1,ROUND_TOP_RIGHT=2,ROUND_BOTTOM_RIGHT=4,ROUND_BOTTOM_LEFT=8;
    int lastLeft=35,lastTop=50,cellWidth=240,cellHeight=180,cellBottom=230,roundings=5;
    MediaViewThumbLocation thumbLocation;boolean useBubbles(){return true;}
    /* WRAPPER */
  }
  static class TGMessage {
    MediaWrapper wrapper=new MediaWrapper();
    MediaViewThumbLocation getMediaThumbLocation(long id,View v,int vt,int vb,int t){return wrapper.getMediaThumbLocation(v,vt,vb,t);}
  }
  static class Adapter {
    TGMessage message=new TGMessage();boolean found=true;
    int findMessageByMediaItem(MediaItem i){return found?0:-1;}
    int indexOfViewByLongId(long id){return found?0:-1;}
    TGMessage getMessage(int i){return message;}
  }
  static class Manager {
    Adapter adapter=new Adapter();RecyclerView recycler;
    Manager(RecyclerView v){recycler=v;}Adapter getAdapter(){return adapter;}
    LayoutManager getLayoutManager(){return recycler.getLayoutManager();}
  }
  static class Pager {Map<Integer,SharedBaseController<?>> cachedItems=new HashMap<>();}
  static class MessagesController implements MediaViewDelegate {
    Manager manager;RecyclerView messagesView;boolean tabs;int pagerScrollPosition;Pager pagerContentAdapter=new Pager();
    MessagesController(RecyclerView r){messagesView=r;manager=new Manager(r);}
    boolean needTabs(){return tabs;}int getTopOffset(){return 0;}
    /* CHAT */
  }
  static class SharedBaseController<T> implements MediaViewDelegate {
    Adapter adapter=new Adapter();RecyclerView recyclerView;Object alternateParent=new Object();
    MediaViewThumbLocation location=new MediaViewThumbLocation();boolean thumbAvailable=true;int innerInset;
    SharedBaseController(RecyclerView r){recyclerView=r;}
    boolean setThumbLocation(MediaViewThumbLocation loc,View v,MediaItem i){loc.left+=innerInset;loc.right-=innerInset;return thumbAvailable;}
    /* SHARED */
  }
  static void check(boolean b,String s){if(!b)throw new AssertionError(s);}
  static void eq(int actual,int expected,String s){check(actual==expected,s+": "+actual+" != "+expected);}
  static class Scene {
    View root=new View(null,0,0),nav=new View(root,0,0);
    RecyclerView list=new RecyclerView(nav,0,220);View row=new View(list,0,180);
    MessagesController chat=new MessagesController(list);SharedBaseController<?> shared=new SharedBaseController<>(list);
    Scene(){list.height=858;list.row=row;}
    void chatBounds(String label){
      MediaViewThumbLocation loc=chat.getTargetLocation(0,new MediaItem());int[] point=new int[2];row.getLocationInWindow(point);
      MediaWrapper w=chat.manager.adapter.message.wrapper;
      eq(loc.left,point[0]+w.lastLeft,label+" chat origin X");eq(loc.top,point[1]+w.lastTop,label+" chat origin Y");
      eq(loc.right-loc.left,w.cellWidth,label+" width");eq(loc.bottom-loc.top,w.cellHeight,label+" height");
      check(loc.noBounce,"bounce flag retained");eq((int)loc.topLeftRadius,12,"roundings retained");
    }
    void sharedBounds(String label){
      MediaViewThumbLocation loc=shared.getTargetLocation(0,new MediaItem());int[] point=new int[2];row.getLocationInWindow(point);
      eq(loc.left,point[0]+shared.innerInset,label+" shared origin X");eq(loc.top,point[1],label+" shared origin Y");
      eq(loc.right,point[0]+row.width-shared.innerInset,label+" shared right");eq(loc.bottom,point[1]+row.height,label+" shared bottom");
    }
  }
  public static void main(String[] args){
    Scene s=new Scene();
    if(args.length>0){s.nav.left=647;if(args[0].equals("chat"))s.chatBounds("negative");else s.sharedBounds("negative");return;}
    s.chatBounds("single");s.sharedBounds("single");
    s.nav.left=647;s.chatBounds("wide");s.sharedBounds("wide");
    for(int x:new int[]{530,750,0,647,0}){s.nav.left=x;s.chatBounds("drag/RTL/fold");s.sharedBounds("drag/RTL/fold");}
    s.root.left=23;s.root.top=11;s.nav.left=647;s.nav.translationX=-37;s.list.translationY=44;s.row.left=13;s.row.translationX=9;s.row.translationY=7;
    s.chatBounds("nested/translated");s.sharedBounds("nested/translated");
    s.chatBounds("repeat");s.chatBounds("close");s.sharedBounds("repeat");
    s.row.top=-80;s.chatBounds("clipped");eq(s.chat.getTargetLocation(0,new MediaItem()).clipTop,30,"top clip retained");
    s.shared.innerInset=11;s.sharedBounds("inner receiver");
    s.chat.tabs=true;s.chat.pagerScrollPosition=1;s.chat.pagerContentAdapter.cachedItems.put(1,s.shared);
    check(s.chat.getTargetLocation(0,new MediaItem())==s.shared.location,"shared tab delegate reused");
    s.shared.thumbAvailable=false;check(s.shared.getTargetLocation(0,new MediaItem())==null,"missing preview");
    s.chat.tabs=false;s.chat.manager.adapter.found=false;check(s.chat.getTargetLocation(0,new MediaItem())==null,"missing chat item");
    s.chat.manager.adapter.found=true;s.list.row=null;check(s.chat.getTargetLocation(0,new MediaItem())==null,"offscreen chat item");
    System.out.println("Media origins: source view bounds, folding/RTL, translation, cache reuse, clipping and delegates passed");
  }
}
"""


class MediaOriginTest(unittest.TestCase):
    def compile_and_run(self, source, *args):
        with tempfile.TemporaryDirectory(prefix="moex-media-origin-") as directory:
            path=Path(directory)/"MediaOriginHarness.java"
            path.write_text(source)
            subprocess.run(["javac", "-d", directory, str(path)], check=True, timeout=30)
            return subprocess.run(["java", "-cp", directory, "MediaOriginHarness", *args], text=True, capture_output=True, timeout=15)

    def test_actual_coordinate_methods(self):
        result=self.compile_and_run(harness())
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_old_pane_local_coordinates_fail(self):
        for route in ("chat", "shared"):
            with self.subTest(route=route):
                result=self.compile_and_run(harness(old=True), route)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("origin X", result.stderr)


if __name__ == "__main__":
    unittest.main()
