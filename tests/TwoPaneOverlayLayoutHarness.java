import java.util.ArrayList;
import java.util.LinkedHashSet;

/** Real overlay callbacks are injected below; only Android window/layout primitives are doubled. */
public final class TwoPaneOverlayLayoutHarness {
  @interface Nullable { }
  static final LinkedHashSet<Runnable> queue = new LinkedHashSet<>();
  static BaseActivity activity;
  static int requests;
  static final class Rect { int left, top, right, bottom; }
  static final class LayoutParams { int leftMargin, topMargin, rightMargin, bottomMargin; }

  static class View {
    interface OnLayoutChangeListener {
      void onLayoutChange(View v, int l, int t, int r, int b, int oldL, int oldT, int oldR, int oldB);
    }
    View parent;
    int left, top, width, height = 900;
    final ArrayList<OnLayoutChangeListener> listeners = new ArrayList<>();
    View () { }
    View (View parent, int left, int width) { this.parent = parent; this.left = left; this.width = width; }
    Object getContext () { return activity; }
    View getParent () { return parent; }
    int getLeft () { return left; }
    int getWidth () { return width; }
    int getMeasuredWidth () { return width; }
    boolean isAttachedToWindow () { return true; }
    View getRootView () { View v=this; while(v.parent!=null)v=v.parent; return v; }
    void getLocationOnScreen (int[] out) { int x=0; for(View v=this;v!=null;v=v.parent)x+=v.left;out[0]=x;out[1]=0; }
    void invalidate () { }
    void requestLayout () { requests++; }
    void setTranslationX (float ignored) { }
    void post (Runnable callback) { queue.add(callback); }
    void removeCallbacks (Runnable callback) { queue.remove(callback); }
    void addOnLayoutChangeListener (OnLayoutChangeListener listener) { listeners.add(listener); }
    void removeOnLayoutChangeListener (OnLayoutChangeListener listener) { listeners.remove(listener); }
    protected void onAttachedToWindow () { }
    protected void onDetachedFromWindow () { }
    public void onApplyMarginInsets (View child, LayoutParams params, Rect legacy, Rect insets, Rect withoutIme) { }
    void layout (int nextLeft, int nextWidth) {
      int oldLeft = left, oldRight = left + width;
      left = nextLeft;
      width = nextWidth;
      if (oldLeft != left || oldRight != left + width) {
        for (OnLayoutChangeListener listener : new ArrayList<>(listeners)) {
          listener.onLayoutChange(this, left, 0, left + width, height, oldLeft, 0, oldRight, height);
        }
      }
    }
  }
  static class RootFrameLayout extends View {
    RootFrameLayout (int left, int width) { super(null, left, width); }
  }
  static final class NavigationController {
    final View pane;
    NavigationController (View pane) { this.pane = pane; }
    View getValue () { return pane; }
    boolean isDestroyed () { return false; }
    boolean isAnimating () { return false; }
    float getHorizontalTranslate () { return 0; }
  }
  static class ViewController<T> {
    NavigationController navigation;
    boolean isDestroyed () { return false; }
    ViewController<T> getParentOrSelf () { return this; }
    ViewController<?> getOptionsSourceController () { return this; }
    BaseActivity context () { return activity; }
    NavigationController navigationController () { return navigation; }
  }
  static final class MessagesController extends ViewController<Object> {
    int getInputOffset (boolean ignored) { return 0; }
    int getPagerScrollOffsetInPixels () { return 0; }
  }
  static final class MoexTwoPane {
    boolean active = true;
    boolean isActive () { return active; }
    boolean isHiddenRoot (ViewController<?> owner) { return false; }
    ViewController<?> leftMain () { return null; }
    boolean isLeftNavigation (NavigationController n) { return false; }
  }
  static final class BaseActivity {
    final MoexTwoPane panes = new MoexTwoPane();
    NavigationController navigation;
    MoexTwoPane moexTwoPane () { return panes; }
    NavigationController navigation () { return navigation; }
  }
  static final class UI {
    static BaseActivity getContext (Object ignored) { return activity; }
    static ViewController<?> getCurrentStackItem (Object ignored) { return null; }
    static void post (Runnable callback) { queue.add(callback); }
  }
  static final class Views {
    static final int[] location = new int[2];
    static int[] getLocationInWindow (View view) {
      int x = 0;
      for (View v = view; v != null; v = v.parent) x += v.left;
      location[0] = x;
      return location;
    }
    static <T> T findAncestor (View view, Class<T> type, boolean ignored) {
      for (View v = view.parent; v != null; v = v.parent) if (type.isInstance(v)) return type.cast(v);
      return null;
    }
    static boolean setMargins (LayoutParams params, int l, int t, int r, int b) {
      boolean changed = params.leftMargin != l || params.topMargin != t || params.rightMargin != r || params.bottomMargin != b;
      params.leftMargin = l; params.topMargin = t; params.rightMargin = r; params.bottomMargin = b;
      return changed;
    }
  }
  interface OffsetProvider { int provideOffset (View view); }

  static final class Inline extends View {
    RootFrameLayout rootView;
    OffsetProvider offsetProvider;
    int lastBottomMargin;
    void setBottomMargin (int value) { lastBottomMargin = value; }
    boolean setInsets (int top, int bottom) { return false; }
    void updateOffset () { }
    /* INLINE_FIELDS */
    /* INLINE_METHODS */
  }

  /* PANE_HELPER */

  static final class Media extends View implements PopupPaneBounds.Provider {
    ViewController<?> parent;
    void setExtraBottomInset (int bottom, int withoutIme) { }
    /* MEDIA_FIELDS */
    /* MEDIA_METHODS */
  }

  static final class Fixture {
    final RootFrameLayout root = new RootFrameLayout(100, 1600);
    final View container = new View(root, 0, 1600);
    final View pane = new View(container, 640, 960);
    final View host = new View(root, 0, 1600);
    final View overlay;
    final LayoutParams params = new LayoutParams();
    final Rect empty = new Rect();
    int targetLeft = 640, targetWidth = 960;

    Fixture (boolean media) {
      queue.clear(); requests = 0;
      activity = new BaseActivity();
      activity.navigation = new NavigationController(pane);
      if (media) {
        Media sheet = new Media();
        ((View) sheet).parent = host;
        sheet.parent = new ViewController<>();
        sheet.parent.navigation = activity.navigation;
        sheet.paneBounds = new PopupPaneBounds(sheet, sheet.parent);
        overlay = sheet;
      } else {
        overlay = new Inline();
        overlay.parent = root;
      }
      overlay.onAttachedToWindow();
    }

    void applyInsets () { overlay.onApplyMarginInsets(overlay, params, empty, empty, empty); }
    void placePane () {
      // FrameLayout performs default placement before the two-pane host's final placement.
      pane.layout(0, targetWidth);
      pane.layout(targetLeft, targetWidth);
    }
    void drainCallbacks () {
      ArrayList<Runnable> callbacks = new ArrayList<>(queue);
      queue.clear();
      for (Runnable callback : callbacks) callback.run();
    }
    int settle () {
      int passes = 0;
      while (requests > 0 || !queue.isEmpty()) {
        if (++passes > 12) throw new AssertionError("overlay layout feedback did not settle");
        if (requests > 0) {
          requests = 0;
          applyInsets();
          placePane();
        }
        drainCallbacks();
      }
      return passes;
    }
  }

  static void check (boolean condition, String message) { if (!condition) throw new AssertionError(message); }

  static void steady (boolean media) {
    Fixture fixture = new Fixture(media);
    fixture.applyInsets();
    fixture.placePane();
    int passes = fixture.settle();
    check(passes <= 1, "unchanged final pane bounds must not trigger another layout");
    check(fixture.params.leftMargin == 640 && fixture.params.rightMargin == 0, "initial right-pane margins applied");
    for (int i = 0; i < 100; i++) {
      fixture.applyInsets(); fixture.placePane(); fixture.settle();
    }
    check(requests == 0 && queue.isEmpty(), "repeated unrelated parent layouts must become idle");
  }

  static void changes (boolean media) {
    Fixture fixture = new Fixture(media);
    fixture.applyInsets(); fixture.placePane(); fixture.settle();
    fixture.targetLeft = 720; fixture.targetWidth = 880;
    fixture.placePane(); fixture.settle();
    check(fixture.params.leftMargin == 720 && fixture.params.rightMargin == 0, "divider drag updates overlay margins");
    activity.panes.active = false;
    fixture.targetLeft = 0; fixture.targetWidth = 1600;
    fixture.placePane(); fixture.settle();
    check(fixture.params.leftMargin == 0 && fixture.params.rightMargin == 0, "fold removes old pane margins");
    activity.panes.active = true;
    fixture.targetLeft = 640; fixture.targetWidth = 960;
    fixture.placePane(); fixture.settle();
    check(fixture.params.leftMargin == 640, "unfold reapplies pane margins");
    fixture.targetLeft = 0; fixture.targetWidth = 960;
    fixture.placePane(); fixture.settle();
    check(fixture.params.leftMargin == 0 && fixture.params.rightMargin == 640, "RTL places margins on trailing side");
  }

  static void detached (boolean media) {
    Fixture fixture = new Fixture(media);
    fixture.applyInsets(); fixture.placePane(); fixture.settle();
    fixture.placePane(); // only the pane callback is pending, not first-attach inset work
    check(!queue.isEmpty(), "bounds changes schedule a callback before detachment");
    fixture.overlay.onDetachedFromWindow();
    check(queue.isEmpty(), "detach cancels scheduled callback");
    fixture.targetLeft = 700; fixture.targetWidth = 900;
    fixture.placePane(); fixture.settle();
    check(requests == 0 && fixture.pane.listeners.isEmpty(), "detach removes pane listener");
  }

  public static void main (String[] args) {
    boolean media = args[0].equals("media");
    switch (args[1]) {
      case "steady": steady(media); break;
      case "changes": changes(media); break;
      case "detach": detached(media); break;
      default: throw new IllegalArgumentException(args[1]);
    }
    System.out.println(args[0] + " " + args[1] + ": passed");
  }
}
