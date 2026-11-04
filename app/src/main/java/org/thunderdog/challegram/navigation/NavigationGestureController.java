/*
 * This file is a part of Telegram X
 * Copyright © 2014 (tgx-android@pm.me)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 *
 * File created on 23/04/2015 at 17:48
 */
package org.thunderdog.challegram.navigation;

import android.content.Context;
import android.graphics.Rect;
import android.os.Build;
import android.view.GestureDetector;
import android.view.MotionEvent;

import androidx.annotation.Nullable;

import org.thunderdog.challegram.BaseActivity;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.tool.UI;
import org.thunderdog.challegram.unsorted.Size;
import org.thunderdog.challegram.widget.RootFrameLayout;

public class NavigationGestureController implements GestureDetector.OnGestureListener {
  private GestureDetector gestureDetector;
  private NavigationController navigation;
  private @Nullable DrawerController drawer;

  private boolean isScrolling;

  private float startX, startY;
  private int lastScrollX, lastScrollY;

  private boolean listenSlidingBack, slidingVertical, slidingBack, slidingDrawer;
  private boolean /*blocked,*/ abortUp;
  //private boolean listenMenuSlide;

  private void clear (boolean releaseInput) {
    startX = 0.0f;
    startY = 0.0f;
    listenSlidingBack = false;
    slidingVertical = false;
    // blocked = false;
    slidingBack = false;
    slidingDrawer = false;
    lastScrollX = -1;
    lastScrollY = -1;

    if (releaseInput && !target().isAnimating()) {
      setInputBlocked(false);
    }
  }

  private boolean inputBlocked;

  private void setInputBlocked (boolean isBlocked) {
    if (this.inputBlocked != isBlocked) {
      this.inputBlocked = isBlocked;
      ((BaseActivity) navigation.getContext()).setIsKeyboardBlocked(isBlocked);
      // UI.getContext(navigation.getContext()).setOrientationLockFlagEnabled(BaseActivity.ORIENTATION_FLAG_TOUCHING_NAVIGATION, isBlocked);
    }
  }

  public NavigationGestureController (Context context, NavigationController navigation, DrawerController drawer) {
    this.gestureDetector = new GestureDetector(context, this);
    this.navigation = navigation;
    this.drawer = drawer;
    clear(false);
  }

  public void onScrollStateChanged (int state) {
    /*boolean isScrolling = state == AbsListView.OnScrollListener.SCROLL_STATE_TOUCH_SCROLL;
    if (this.isScrolling != isScrolling) {
      // this.isScrolling = isScrolling;
    }*/
  }

  public boolean onTouchEvent (MotionEvent event) {
    switch (event.getAction()) {
      case MotionEvent.ACTION_UP: {
        gestureDetector.onTouchEvent(event);
        return onUp(event);
      }
      case MotionEvent.ACTION_MOVE: {
        gestureDetector.onTouchEvent(event);
        return onDrag(event);
      }
      case MotionEvent.ACTION_DOWN: {
        gestureDetector.onTouchEvent(event);
        return true;
      }
      default: {
        return gestureDetector.onTouchEvent(event);
      }
    }
  }

  // Two-pane gesture routing adapted from XGram (MoexTwoPane: chat list | chat) a gesture acts on the pane it starts in, as if that pane
  // were the whole screen. In the chat list pane the side menu opens from the screen edge (or the pane's own screens
  // slide back) and the folder pager keeps its swipes; in the chat pane the chat slides back from its leading edge,
  // next to the divider; over the "select a chat" placeholder nothing happens. Touches come in the content view's
  // coordinates (the whole screen): the system gesture edges are checked with those, and the screens get them in
  // their own pane's coordinates, as with one pane. One pane: exactly Telegram X.

  /** The navigation the current gesture acts on: {@link #navigation}, or the chat list pane's. */
  private NavigationController target;
  /** Where {@link #target}'s view starts in the content view: 0 with one pane. */
  private int targetLeft;

  private NavigationController target () {
    NavigationController target = this.target;
    return target != null && !target.isDestroyed() ? target : navigation;
  }

  @Nullable
  private moe.kirao.mgx.layout.MoexTwoPane moexTwoPane () {
    moe.kirao.mgx.layout.MoexTwoPane twoPane = ((BaseActivity) navigation.getContext()).moexTwoPane();
    return twoPane != null && twoPane.isActive() ? twoPane : null;
  }

  /**
   * Picks the pane a gesture starting at {@code x} (content view coordinates) acts on.
   *
   * @return false when no gesture starts there: the placeholder of the chat pane, the line between the panes
   */
  private boolean moexPickPane (float x, boolean drawerVisible) {
    target = navigation;
    targetLeft = 0;
    NavigationController list = moe.kirao.mgx.layout.MoexTwoPaneGestures.listNavigation((BaseActivity) navigation.getContext());
    if (list == null || list == navigation) {
      return true; // one pane
    }
    if (drawerVisible) {
      // The side menu belongs to the chat list pane: dragging it or tapping beside it, anywhere.
      target = list;
      targetLeft = list.getValue().getLeft();
      return true;
    }
    android.view.View listView = list.getValue(), chatView = navigation.getValue();
    if (x >= listView.getLeft() && x < listView.getRight()) {
      target = list;
      targetLeft = listView.getLeft();
      return true;
    }
    if (x >= chatView.getLeft() && x < chatView.getRight()) {
      targetLeft = chatView.getLeft();
      // At its root the chat pane shows the placeholder over its hidden chat list: nothing to slide back.
      return navigation.getStackSize() > 1;
    }
    return false;
  }

  /** The width the side menu opens in: the screen's, also with two panes. */
  private int moexDrawerSpaceWidth () {
    android.view.View view = navigation.getValue();
    if (moexTwoPane() != null && view.getParent() instanceof android.view.View) {
      return ((android.view.View) view.getParent()).getMeasuredWidth();
    }
    return view.getMeasuredWidth();
  }

  public boolean onDown (MotionEvent event) {
    target = navigation; // XGram: until the pane is picked below
    targetLeft = 0;
    if (navigation.isDestroyed() || navigation.isAnimating())
      return false;

    startX = event.getX(0);
    startY = event.getY(0);

    if (startY <= 0f) //HeaderView.getSize()
      return false;

    final boolean drawerVisible = drawer != null && drawer.isVisible();
    if (!moexPickPane(startX, drawerVisible)) {
      return false;
    }
    final NavigationController target = target();
    if (target != navigation && target.isAnimating()) {
      return false;
    }

    ViewController<?> c = target.getCurrentStackItem();

    if (c == null || c.isIntercepted())
      return false;

    listenSlidingBack = (drawerVisible || (!isScrolling && canSlideBack(c, startX, startY)));
    slidingVertical = listenSlidingBack && c.usePopupMode();

    return listenSlidingBack;
  }

  private boolean canSlideBack () {
    final NavigationController navigation = target();
    int stackSize = navigation.getStackSize();
    ViewController<?> c = navigation.getCurrentStackItem();
    return navigation.swipeNavigationEnabled() && stackSize > 0 && c != null && c.swipeNavigationEnabled() && !c.forceFadeMode() && !c.inSelectMode() && !c.inCustomMode() && !(stackSize == 1 && c.inSearchMode());
  }

  private boolean canSlideBack (ViewController<?> c, float x, float y) {
    final NavigationController navigation = target();
    int stackSize = navigation.getStackSize();
    if (navigation.swipeNavigationEnabled() && stackSize > 0 && c != null){
      if (c.swipeNavigationEnabled() && !c.forceFadeMode() && !c.inSelectMode() && !c.inCustomMode() && !(stackSize == 1 && c.inSearchMode()) && c.canSlideBackFrom(navigation, x - targetLeft, y)) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
          RootFrameLayout rootFrameLayout = UI.getContext(navigation.getContext()).getRootView();
          Rect gestureInsets = rootFrameLayout.getSystemGesturesInsets();
          if (x < gestureInsets.left || x > rootFrameLayout.getMeasuredWidth() - gestureInsets.right) {
            return false;
          }
        }
        return true;
      }
    }
    return false;
  }

  public void onCancel () {
    abortUp = false;
    final NavigationController navigation = target();
    if (slidingBack) {
      navigation.forceClosePreview();
      navigation.setIsAnimating(false);
    } else if (slidingDrawer && drawer != null) {
      drawer.forceDrop();
    }
    clear(true);
  }

  public boolean onUp (MotionEvent event) {
    if (abortUp) {
      clear(true);
      return abortUp = false;
    }

    final NavigationController navigation = target();
    if (listenSlidingBack && drawer != null && drawer.isVisible()) {
      boolean ok;
      if (Lang.rtl()) {
        ok = event.getX() < moexDrawerSpaceWidth() - drawer.getWidth() + drawer.getShadowWidth();
      } else {
        ok = event.getX() >= drawer.getWidth();
      }
      if (ok) {
        drawer.close(0f, null);
      }
    } else if (slidingBack) {
      boolean close;

      if (slidingVertical) {
        close = lastScrollY < (float) navigation.getValue().getMeasuredHeight() * Size.NAVIGATION_DROP_FACTOR;
      } else {
        close = lastScrollX < (float) navigation.getValue().getMeasuredWidth() * Size.NAVIGATION_DROP_FACTOR;
      }

      if (close) {
        navigation.closePreview(0f);
      } else {
        navigation.applyPreview(0f);
      }
    } else if (drawer != null && slidingDrawer) {
      drawer.drop();
    }

    clear(true);

    return false;
  }

  public boolean onFling (MotionEvent event, MotionEvent event2, float velocityX, float velocityY) {
    float velocity = slidingVertical ? velocityY : velocityX;
    float abs = Math.abs(velocity);

    if (abs > Screen.dp(250, 1f)) {
      abortUp = true;

      final NavigationController navigation = target();
      if (slidingBack) {
        if ((velocity < 0 && (!Lang.rtl() || slidingVertical)) || (velocity >= 0 && Lang.rtl() && !slidingVertical)) {
          navigation.closePreview(abs);
        } else {
          navigation.applyPreview(abs);
        }
      } else if (slidingDrawer && drawer != null) {
        if ((velocityX < 0 && !Lang.rtl()) || (velocityX >= 0 && Lang.rtl())) {
          drawer.close(abs, null);
        } else {
          drawer.open(abs);
        }
      }

      clear(false);
    } else {
      abortUp = false;
    }

    return abortUp;
  }

  public boolean onScroll (MotionEvent event, MotionEvent event2, float velocityX, float velocityY) {
    return slidingBack || slidingDrawer;
  }

  public boolean onDrag (MotionEvent event) {
    lastScrollX = (int) Math.floor(event.getX(0) - startX);
    lastScrollY = slidingVertical ? (int) Math.floor(Math.max(0f, event.getY(0) - startY)) : 0;

    final NavigationController navigation = target();
    if (slidingBack) {
      navigation.translatePreview(slidingVertical ? lastScrollY : lastScrollX);
      return slidingBack;
    } else if (slidingDrawer && drawer != null) {
      if (drawer.isVisible()) {
        lastScrollX = (int) (event.getX(0) - startX);
      }
      drawer.translate(lastScrollX);
      return false;
    }

    if (listenSlidingBack) {
      float diffX = event.getX(0) - startX;
      float diffY = event.getY(0) - startY;

      if (drawer != null && drawer.isVisible() && (Math.abs(diffX) >= Screen.getTouchSlop() /*|| Math.abs(diffY) > Size.TOUCH_SLOP_Y*/)) {
        startX += diffX;

        if (!canSlideBack()) {
          listenSlidingBack = false;
          return false;
        } listenSlidingBack = false;

        if (!drawer.prepare()) {
          listenSlidingBack = false;
          return false;
        }

        slidingDrawer = true;
      } else {
        boolean approve;

        if (slidingVertical) {
          approve = diffY >= Screen.getTouchSlopBig() && Math.abs(diffX) <= Screen.getTouchSlopY();
        } else if (Lang.rtl()) {
          approve = diffX <= -Screen.getTouchSlopBig() && Math.abs(diffY) <= Screen.getTouchSlopY();
        } else {
          approve = diffX >= Screen.getTouchSlopBig() && Math.abs(diffY) <= Screen.getTouchSlopY();
        }

        if (!approve) {
          return false;
        }

        if (!canSlideBack()) {
          listenSlidingBack = false;
          return false;
        }

        startX += diffX;
        startY += diffY;

        listenSlidingBack = false;
        slidingBack = navigation.getStackSize() > 1;

        setInputBlocked(true);

        if (slidingBack) {
          if (!navigation.openPreview(event.getY())) {
            slidingBack = false;
            listenSlidingBack = false;
            return false;
          }
        } else {
          if (drawer == null || !drawer.prepare()) {
            listenSlidingBack = false;
            return false;
          }
          slidingDrawer = true;
        }

        onDrag(event);

        return true;
      }
    }

    return false;
  }

  public boolean isDispatching () {
    return slidingBack || slidingDrawer;
  }

  public boolean onSingleTapUp (MotionEvent event) {
    return false;
  }

  public void onShowPress (MotionEvent event) { }
  public void onLongPress (MotionEvent event) { }

}
