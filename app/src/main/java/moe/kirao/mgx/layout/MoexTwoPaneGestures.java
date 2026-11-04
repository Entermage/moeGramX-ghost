/*
 * This file is a part of XGram, a fork of Telegram X
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
package moe.kirao.mgx.layout;

import androidx.activity.BackEventCompat;
import androidx.annotation.Nullable;

import org.thunderdog.challegram.BaseActivity;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.navigation.BackPressMode;
import org.thunderdog.challegram.navigation.DrawerController;
import org.thunderdog.challegram.navigation.NavigationController;
import org.thunderdog.challegram.ui.MainController;

/**
 * Two panes ({@link MoexTwoPane}): the system back gesture acts on the pane at the screen edge it starts from, like
 * the app's own swipes (NavigationGestureController picks the pane a swipe starts in).
 * <ul>
 *   <li>A back swipe from the chat list's edge (left, right in right-to-left languages) goes back in the chat list
 *   pane when it has a screen of its own to leave (an archive, a folder's chats); otherwise it does what back
 *   always does there.</li>
 *   <li>The side menu, open over the chat list, closes before anything in the chat pane.</li>
 * </ul>
 * With one pane nothing here applies.
 */
public final class MoexTwoPaneGestures {
  private MoexTwoPaneGestures () { }

  /** The chat list pane's navigation while two panes are shown, else null. */
  @Nullable
  public static NavigationController listNavigation (@Nullable BaseActivity context) {
    MoexTwoPane twoPane = context != null ? context.moexTwoPane() : null;
    MainController leftMain = twoPane != null ? twoPane.leftMain() : null; // null unless two panes are shown
    NavigationController list = leftMain != null ? leftMain.navigationController() : null;
    return list != null && list != context.navigation() && !list.isDestroyed() ? list : null;
  }

  /** Whether a system back swipe from {@code swipeEdge} (BackEventCompat.EDGE_*) starts at the chat list's edge. */
  public static boolean isListEdge (int swipeEdge) {
    return Lang.rtl() ? swipeEdge == BackEventCompat.EDGE_RIGHT : swipeEdge == BackEventCompat.EDGE_LEFT;
  }

  /**
   * The navigation a predictive back gesture from {@code swipeEdge} should go back in when that is the chat list
   * pane's, else null (the usual target). If the right pane is at its placeholder, either edge
   * targets the list pane, matching the committed Back action.
   */
  @Nullable
  public static NavigationController backTargetForEdge (@Nullable BaseActivity context, int swipeEdge) {
    if (context == null || closesDrawerFirst(context)) {
      return null;
    }
    if (!isListEdge(swipeEdge) && context.navigation().getStackSize() > 1) {
      return null;
    }
    NavigationController list = listNavigation(context);
    if (list == null || list.isAnimating() || list.getStackSize() <= 1) {
      return null;
    }
    return list.performOnBackPressed(false, false) == BackPressMode.NAVIGATE_BACK_IN_STACK ? list : null;
  }

  /** Two panes with the side menu open: back closes it first, whatever is open in the chat pane. */
  public static boolean closesDrawerFirst (@Nullable BaseActivity context) {
    if (context == null) {
      return false;
    }
    DrawerController drawer = context.getDrawer();
    MoexTwoPane twoPane = context.moexTwoPane();
    return drawer != null && drawer.isVisible() && twoPane != null && twoPane.isActive();
  }
}
