package org.thunderdog.challegram.navigation;

import android.graphics.Rect;
import android.view.View;
import android.widget.FrameLayout;

import androidx.annotation.Nullable;

import org.thunderdog.challegram.BaseActivity;
import org.thunderdog.challegram.tool.Views;

import moe.kirao.mgx.layout.MoexTwoPane;

/** Shared source-pane geometry for menus, settings and controller-backed sheets. */
public final class PopupPaneBounds {
  public interface Provider {
    @Nullable PopupPaneBounds getPopupPaneBounds ();
  }

  private final View content;
  private final @Nullable ViewController<?> parent;
  private final BaseActivity activity;
  private final @Nullable NavigationController sourceNavigation;

  public PopupPaneBounds (View content, ViewController<?> source) {
    this.content = content;
    this.parent = source;
    this.activity = source.context();
    this.sourceNavigation = null;
  }

  /** Global header controls belong to a navigation even when its root list is hidden. */
  public PopupPaneBounds (View content, BaseActivity activity, NavigationController navigation) {
    this.content = content;
    this.parent = null;
    this.activity = activity;
    this.sourceNavigation = navigation;
  }

  private int sourcePaneLeft, sourcePaneRight;
  private final int[] paneLocation = new int[2], popupLocation = new int[2];
  private @Nullable View watchedPane, watchedPopup;
  private @Nullable View.OnLayoutChangeListener paneLayoutListener;
  private @Nullable Runnable updatePaneLayout;

  private @Nullable View sourcePaneView (boolean requireActive) {
    if (parent != null && parent.isDestroyed()) return null;
    MoexTwoPane panes = activity.moexTwoPane();
    if (panes == null || (requireActive && !panes.isActive())) return null;
    NavigationController navigation = sourceNavigation;
    if (navigation == null) {
      ViewController<?> owner = parent != null ? parent.getOptionsSourceController() : null;
      if (panes.isHiddenRoot(owner)) owner = panes.leftMain();
      if (owner == null || owner.isDestroyed()) return null;
      navigation = owner.navigationController();
    }
    // A controller inside a full-screen popup has no pane navigation. Never fall back
    // to the right navigation: media-viewer menus must keep their full-screen scope.
    if (navigation == null || navigation.isDestroyed() ||
        (navigation != activity.navigation() && !panes.isLeftNavigation(navigation))) return null;
    return navigation.getValue();
  }

  public @Nullable View getSourcePaneView () {
    View pane = sourcePaneView(true);
    return pane != null && pane.isAttachedToWindow() && pane.getParent() != null && pane.getWidth() > 0 ? pane : null;
  }

  public boolean update () {
    if (watchedPopup != null) watchSourcePane();
    int left = 0, right = 0;
    View pane = sourcePaneView(true);
    View popup = content.getParent() instanceof View ? (View) content.getParent() : null;
    if (pane != null && pane.isAttachedToWindow() && pane.getParent() != null && pane.getWidth() > 0 && popup != null) {
      int width = popup.getWidth();
      if (width <= 0) width = pane.getRootView().getWidth();
      pane.getLocationOnScreen(paneLocation);
      popup.getLocationOnScreen(popupLocation);
      int paneLeft = paneLocation[0] - popupLocation[0];
      int paneRight = paneLeft + pane.getWidth();
      if (width > 0 && paneRight > 0 && paneLeft < width) {
        left = Math.max(0, paneLeft);
        right = Math.max(0, width - paneRight);
      }
    }
    boolean changed = sourcePaneLeft != left || sourcePaneRight != right;
    sourcePaneLeft = left;
    sourcePaneRight = right;
    return changed;
  }

  private void watchSourcePane () {
    if (updatePaneLayout == null) {
      updatePaneLayout = () -> {
        watchSourcePane();
        View popup = content.getParent() instanceof View ? (View) content.getParent() : null;
        if (popup != null && update()) {
          popup.requestLayout();
          popup.invalidate();
        }
      };
      paneLayoutListener = (v, l, t, r, b, oldL, oldT, oldR, oldB) -> {
        if (l != oldL || r != oldR) {
          content.removeCallbacks(updatePaneLayout);
          content.post(updatePaneLayout); // use final bounds after the two-pane layout pass
        }
      };
    }
    View pane = sourcePaneView(false);
    View popup = content.getParent() instanceof View ? (View) content.getParent() : null;
    if (watchedPane == pane && watchedPopup == popup) return;
    unwatchSourcePane();
    watchedPane = pane;
    watchedPopup = popup;
    if (watchedPane != null) watchedPane.addOnLayoutChangeListener(paneLayoutListener);
    if (watchedPopup != null) watchedPopup.addOnLayoutChangeListener(paneLayoutListener);
    content.post(updatePaneLayout);
  }

  private void unwatchSourcePane () {
    if (watchedPane != null) watchedPane.removeOnLayoutChangeListener(paneLayoutListener);
    if (watchedPopup != null) watchedPopup.removeOnLayoutChangeListener(paneLayoutListener);
    watchedPane = watchedPopup = null;
    if (updatePaneLayout != null) content.removeCallbacks(updatePaneLayout);
  }

  public void attach () {
    watchSourcePane();
  }

  public void detach () {
    unwatchSourcePane();
  }

  public void applyInsets (FrameLayout.LayoutParams params, Rect insets) {
    update();
    Views.setMargins(params, Math.max(insets.left, sourcePaneLeft), 0, Math.max(insets.right, sourcePaneRight), 0);
  }

  public boolean isConstrained () {
    return sourcePaneLeft > 0 || sourcePaneRight > 0;
  }

  public int getLeftInset () { return sourcePaneLeft; }
  public int getRightInset () { return sourcePaneRight; }

  /** Width is available before the menu is attached, for grid columns and text measurement. */
  public int getAvailableWidth (int fullWidth) {
    View pane = sourcePaneView(true);
    return pane != null && pane.isAttachedToWindow() && pane.getWidth() > 0 ? Math.min(fullWidth, pane.getWidth()) : fullWidth;
  }
}
