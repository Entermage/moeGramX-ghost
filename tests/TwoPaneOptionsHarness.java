import java.util.ArrayList;
import java.util.LinkedHashSet;

public final class TwoPaneOptionsHarness {
  @interface Nullable { }
  static final LinkedHashSet<Runnable> queue = new LinkedHashSet<>();
  static int requests;
  static class Rect { int left, right, bottom; }
  static class FrameLayout { static class LayoutParams { int leftMargin, topMargin, rightMargin, bottomMargin; } }
  static class Canvas {
    int left = -1, right = -1;
    int save () { return 1; }
    void clipRect (int l, int t, int r, int b) { left = l; right = r; }
    void restoreToCount (int count) { }
    void drawRect (int l, int t, int r, int b, Object paint) { }
  }
  static class View {
    interface OnLayoutChangeListener { void onLayoutChange (View v, int l, int t, int r, int b, int oldL, int oldT, int oldR, int oldB); }
    View parent;
    int left, width, height = 1200;
    boolean attached = true;
    final ArrayList<OnLayoutChangeListener> listeners = new ArrayList<>();
    View () { }
    View (View parent, int left, int width) { this.parent = parent; this.left = left; this.width = width; }
    View getParent () { return parent; }
    View getRootView () { return parent == null ? this : parent.getRootView(); }
    boolean isAttachedToWindow () { return attached; }
    int getLeft () { return left; }
    int getRight () { return left + width; }
    int getWidth () { return width; }
    int getMeasuredWidth () { return width; }
    int getHeight () { return height; }
    void getLocationOnScreen (int[] out) { out[0] = left; for (View p=parent; p!=null; p=p.parent) out[0] += p.left; }
    void requestLayout () { requests++; }
    void invalidate () { }
    void post (Runnable callback) { queue.add(callback); }
    void removeCallbacks (Runnable callback) { queue.remove(callback); }
    void addOnLayoutChangeListener (OnLayoutChangeListener listener) { listeners.add(listener); }
    void removeOnLayoutChangeListener (OnLayoutChangeListener listener) { listeners.remove(listener); }
    protected void onAttachedToWindow () { }
    protected void onDetachedFromWindow () { }
    public void onApplyMarginInsets (View child, FrameLayout.LayoutParams params, Rect legacy, Rect insets, Rect withoutIme) { }
    public void draw (Canvas canvas) { }
    void layout (int nextLeft, int nextWidth) {
      int oldLeft=left, oldRight=left+width;
      left=nextLeft; width=nextWidth;
      if (oldLeft!=left || oldRight!=left+width)
        for (OnLayoutChangeListener listener:new ArrayList<>(listeners)) listener.onLayoutChange(this,left,0,left+width,height,oldLeft,0,oldRight,height);
    }
  }
  static class NavigationController {
    final View view;
    boolean destroyed;
    NavigationController (View view) { this.view=view; }
    boolean isDestroyed () { return destroyed; }
    View getValue () { return view; }
  }
  static class MoexTwoPane {
    boolean active=true;
    NavigationController left;
    ViewController<?> hiddenRoot, list;
    boolean isHiddenRoot (ViewController<?> c) { return active && c!=null && c==hiddenRoot; }
    ViewController<?> leftMain () { return active ? list : null; }
    boolean isActive () { return active; }
    boolean isLeftNavigation (NavigationController navigation) { return navigation==left; }
  }
  static class BaseActivity {
    final MoexTwoPane panes=new MoexTwoPane();
    NavigationController right;
    MoexTwoPane moexTwoPane () { return panes; }
    NavigationController navigation () { return right; }
  }
  static class ViewController<T> {
    BaseActivity activity;
    NavigationController navigation;
    ViewController<?> wrapper;
    boolean destroyed;
    BaseActivity context () { return activity; }
    boolean isDestroyed () { return destroyed; }
    ViewController<?> getParentOrSelf () { return wrapper!=null ? wrapper : this; }
    NavigationController navigationController () { return navigation; }
    /* SOURCE_CONTROLLER */
  }
  static class DrawerController extends ViewController<Void> {
    /* DRAWER_SOURCE */
  }
  static class Views {
    static void setMargins (FrameLayout.LayoutParams p,int l,int t,int r,int b) { p.leftMargin=l; p.topMargin=t; p.rightMargin=r; p.bottomMargin=b; }
    static void setPaddingBottom (View view,int bottom) { }
  }
  /* HELPER */
  static class OptionsLayout extends View implements PopupPaneBounds.Provider {
    final ViewController<?> parent;
    OptionsLayout (ViewController<?> source, View popup) { this.parent=source; super.parent=popup; }
    private PopupPaneBounds paneBounds;
    /* METHODS */
  }
  static class SettingsWrapLayout extends View implements PopupPaneBounds.Provider {
    final PopupPaneBounds paneBounds;
    int bottomInset;
    SettingsWrapLayout (ViewController<?> source,View popup) { parent=popup; paneBounds=new PopupPaneBounds(this,source); }
    public PopupPaneBounds getPopupPaneBounds () { return paneBounds; }
    void setBottomInset (int value) { bottomInset=value; }
    /* SETTINGS_INSETS */
  }
  static class ColorUtils { static int color (int alpha,int color) { return color; } }
  static class HeaderView { static int getTopOffset () { return 50; } }
  static class Paints { static Object fillingPaint (int color) { return null; } }
  static class Background extends View {
    View boundView;
    boolean useStatusBar=true;
    boolean dirty=true;
    Canvas cached;
    @Override void invalidate () { dirty=true; }
    Canvas render () {
      if (dirty) { cached=new Canvas(); draw(cached); dirty=false; }
      return cached;
    }
    /* DRAW */
  }
  static class PopupBase extends View {
    View boundView;
    int targetLeft, targetWidth;
    protected void onLayout (boolean changed,int l,int t,int r,int b) {
      boundView.layout(targetLeft,targetWidth);
    }
  }
  static class PopupHost extends PopupBase {
    final Background backgroundView=new Background();
    /* POPUP_LAYOUT */
  }
  static final class Fixture {
    final View screen=new View(null,100,1600);
    final View content=new View(screen,0,1600);
    final View pane=new View(content,644,956);
    final View popup=new View(null,100,1600);
    final BaseActivity activity=new BaseActivity();
    final ViewController<?> source;
    final FrameLayout.LayoutParams params=new FrameLayout.LayoutParams();
    final Rect insets=new Rect();
    final OptionsLayout options;
    Fixture () { this(new ViewController<>()); }
    Fixture (ViewController<?> controller) {
      source=controller;
      queue.clear(); requests=0;
      activity.right=new NavigationController(pane);
      source.activity=activity; source.navigation=source instanceof DrawerController ? null : activity.right;
      options=new OptionsLayout(source,popup);
      options.setConstrainToSourcePane();
      options.onAttachedToWindow();
    }
    void apply () { options.onApplyMarginInsets(options,params,insets,insets,insets); options.layout(params.leftMargin,popup.width-params.leftMargin-params.rightMargin); }
    void drain () {
      int count=0;
      while (!queue.isEmpty() || requests>0) {
        check(++count<12,"layout feedback must settle");
        if (requests>0) { requests=0; apply(); }
        ArrayList<Runnable> jobs=new ArrayList<>(queue); queue.clear();
        for(Runnable job:jobs) job.run();
      }
    }
    void checkBounds (int left,int right) {
      apply(); drain();
      check(params.leftMargin==left && params.rightMargin==right,"menu follows source pane: "+params.leftMargin+","+params.rightMargin);
      Background background=new Background(); background.boundView=options; background.width=popup.width; background.parent=popup;
      Canvas canvas=new Canvas(); background.draw(canvas);
      if(left>0 || right>0) check(canvas.left==left && canvas.right==popup.width-right,"dim follows same bounds");
      else check(canvas.left==-1,"full-width overlay must not be clipped");
    }
  }
  static void check (boolean condition,String message) { if(!condition) throw new AssertionError(message); }
  static void bounds () {
    Fixture f=new Fixture(); f.checkBounds(644,0);
    f.pane.layout(0,956); f.checkBounds(0,644); // RTL right navigation
    f.activity.panes.left=f.activity.right; f.activity.right=new NavigationController(new View(f.content,644,956));
    f.pane.layout(0,620); f.checkBounds(0,980); // originating left navigation
    f.pane.layout(40,580); f.insets.left=40; f.checkBounds(40,980); // no double inset
    ViewController<?> page=new ViewController<>(); page.activity=f.activity; page.wrapper=f.source;
    OptionsLayout nested=new OptionsLayout(page,f.popup); nested.setConstrainToSourcePane();
    nested.onApplyMarginInsets(nested,f.params,f.insets,f.insets,f.insets);
    check(f.params.leftMargin==40 && f.params.rightMargin==980,"pager inherits wrapper pane");
  }
  static void scope () {
    Fixture f=new Fixture(); f.checkBounds(644,0);
    f.activity.panes.active=false; f.checkBounds(0,0);
    f.activity.panes.active=true; f.source.navigation=null; f.checkBounds(0,0); // full-screen media
    f.source.navigation=new NavigationController(f.pane); f.checkBounds(0,0); // foreign navigation
    f.source.navigation=f.activity.right; f.source.destroyed=true; f.checkBounds(0,0);
    f.source.destroyed=false;
    PopupPaneBounds headerBounds = new PopupPaneBounds(f.options, f.activity, f.activity.right);
    check(headerBounds.getSourcePaneView()==f.pane,"global player header owns its navigation without an open chat");
    f.activity.panes.hiddenRoot=f.source;
    check(headerBounds.getSourcePaneView()==f.pane,"global header never remaps to hidden-root left pane");
    f.activity.panes.hiddenRoot=null;
    f.activity.panes.active=false;
    check(headerBounds.getSourcePaneView()==null,"single pane removes global header constraint");
    f.activity.panes.active=true;
    f.pane.attached=false; f.checkBounds(0,0);
    f.pane.attached=true; f.options.paneBounds=null; f.checkBounds(0,0);
  }
  static void lifecycle () {
    Fixture f=new Fixture(); f.checkBounds(644,0);
    for(int i=0;i<100;i++) { f.pane.layout(0,956); f.pane.layout(644,956); f.drain(); }
    check(requests==0 && queue.isEmpty(),"temporary pane positions must not keep requesting layout");
    f.pane.layout(720,880); f.drain(); f.checkBounds(720,0);
    f.activity.panes.active=false; f.pane.layout(0,750); f.popup.layout(100,750); f.drain(); f.checkBounds(0,0);
    f.activity.panes.active=true; f.pane.layout(644,956); f.popup.layout(100,1600); f.drain(); f.checkBounds(644,0);
    ViewController<?> list = new ViewController<>(); list.activity=f.activity;
    View leftPane=new View(f.content,0,620); list.navigation=new NavigationController(leftPane);
    f.activity.panes.hiddenRoot=f.source; f.activity.panes.list=list; f.activity.panes.left=list.navigation;
    f.checkBounds(0,980);
    check(f.pane.listeners.isEmpty() && leftPane.listeners.size()==1,"hidden root binds to visible list and moves listener");
    f.activity.panes.hiddenRoot=null; f.checkBounds(644,0);
    check(leftPane.listeners.isEmpty() && f.pane.listeners.size()==1,"source rebinding removes obsolete listener");
    f.pane.layout(700,900); check(!queue.isEmpty(),"pending update before detach");
    f.options.onDetachedFromWindow();
    check(queue.isEmpty() && f.pane.listeners.isEmpty() && f.popup.listeners.isEmpty(),"detach cancels listeners and pending update");
  }
  static void drawer () {
    Fixture f=new Fixture(new DrawerController());
    check(f.source.navigation==null,"drawer has no navigation of its own");
    View leftPane=new View(f.content,0,620);
    ViewController<?> list=new ViewController<>(); list.activity=f.activity; list.navigation=new NavigationController(leftPane);
    f.activity.panes.list=list; f.activity.panes.left=list.navigation;
    f.checkBounds(0,980);
    check(f.pane.listeners.isEmpty() && leftPane.listeners.size()==1,"drawer confirmation watches left pane only");
    f.activity.panes.active=false; f.popup.layout(100,750); f.drain(); f.checkBounds(0,0);
    check(leftPane.listeners.isEmpty(),"fold unbinds drawer from left pane");
    f.activity.panes.active=true; f.popup.layout(100,1600); f.drain(); f.checkBounds(0,980);
    check(leftPane.listeners.size()==1,"unfold resolves drawer to left pane again");
    ViewController<?> nestedSource=new ViewController<>(); nestedSource.activity=f.activity; nestedSource.wrapper=f.source;
    OptionsLayout nested=new OptionsLayout(nestedSource,f.popup); nested.setConstrainToSourcePane();
    nested.onApplyMarginInsets(nested,f.params,f.insets,f.insets,f.insets);
    check(f.params.leftMargin==0 && f.params.rightMargin==980,"wrapped drawer menus inherit explicit source");
    View replacementPane=new View(f.content,0,700);
    ViewController<?> replacementList=new ViewController<>(); replacementList.activity=f.activity; replacementList.navigation=new NavigationController(replacementPane);
    f.activity.panes.list=replacementList; f.activity.panes.left=replacementList.navigation;
    f.checkBounds(0,900);
    check(leftPane.listeners.isEmpty() && replacementPane.listeners.size()==1,"drawer source replacement removes old listeners");
    f.options.onDetachedFromWindow();
    check(replacementPane.listeners.isEmpty() && f.popup.listeners.isEmpty() && queue.isEmpty(),"drawer menu cleanup releases its source");
    Fixture settings=new Fixture(); settings.checkBounds(644,0);
    Fixture media=new Fixture(); media.source.navigation=null; media.checkBounds(0,0);
  }
  static void settings () {
    Fixture f=new Fixture();
    SettingsWrapLayout settings=new SettingsWrapLayout(f.source,f.popup);
    settings.paneBounds.attach();
    Rect withIme=new Rect(); withIme.bottom=400;
    Rect withoutIme=new Rect(); withoutIme.bottom=24;
    settings.onApplyMarginInsets(settings,f.params,f.insets,withIme,withoutIme);
    check(f.params.leftMargin==644 && f.params.rightMargin==0,"settings sheet follows right source");
    check(f.params.bottomMargin==0 && settings.bottomInset==24,"settings keeps footer system inset without applying IME as footer");
    Background background=new Background(); background.boundView=settings; background.parent=f.popup;
    Canvas canvas=new Canvas(); background.draw(canvas);
    check(canvas.left==644 && canvas.right==1600,"settings dim covers source pane");
    // A narrow More menu is positioned within a pane; its dim must still cover the entire pane.
    settings.layout(1300,180);
    Canvas narrowMenuDim=new Canvas(); background.draw(narrowMenuDim);
    check(narrowMenuDim.left==644 && narrowMenuDim.right==1600,"narrow menu dims its full source pane");
    f.activity.panes.left=f.activity.right; f.activity.right=new NavigationController(new View(f.content,644,956));
    f.pane.layout(0,620);
    settings.onApplyMarginInsets(settings,f.params,f.insets,withIme,withoutIme);
    check(f.params.leftMargin==0 && f.params.rightMargin==980,"batch confirmation in left pane");
    f.activity.panes.active=false;
    settings.onApplyMarginInsets(settings,f.params,f.insets,withIme,withoutIme);
    check(f.params.leftMargin==0 && f.params.rightMargin==0 && settings.bottomInset==24,"single pane settings preserves footer inset");
    settings.paneBounds.detach();
  }
  static void dimCache () {
    Fixture f=new Fixture();
    PopupHost host=new PopupHost(); host.boundView=f.options; host.backgroundView.boundView=f.options; host.backgroundView.parent=f.popup;
    f.checkBounds(644,0);
    host.targetLeft=644; host.targetWidth=956;
    host.onLayout(true,0,0,1600,1200);
    check(host.backgroundView.render().left==644,"initial right-pane dim");
    int previousRequests=requests;
    f.activity.panes.active=false; f.pane.layout(0,750); f.popup.layout(100,750); f.drain(); f.apply();
    host.targetLeft=0; host.targetWidth=750;
    host.onLayout(true,0,0,750,1200);
    check(host.backgroundView.render().left==-1,"dim cache refreshed when folding to full width");
    f.activity.panes.active=true; f.pane.layout(644,956); f.popup.layout(100,1600); f.drain(); f.apply();
    host.targetLeft=644; host.targetWidth=956;
    host.onLayout(true,0,0,1600,1200);
    Canvas dim=host.backgroundView.render();
    check(dim.left==644 && dim.right==1600,"dim cache refreshed when unfolding to right pane");
    check(requests==previousRequests,"dim invalidation must not request another layout");
  }
  public static void main (String[] args) {
    switch(args[0]) { case "bounds": bounds(); break; case "scope": scope(); break; case "lifecycle": lifecycle(); break; case "dim_cache": dimCache(); break; case "drawer": drawer(); break; case "settings": settings(); break; default: throw new AssertionError(args[0]); }
  }
}
