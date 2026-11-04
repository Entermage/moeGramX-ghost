/*
 * This file is a part of moeGramX, adapted from XGram's XgramTwoPane.
 * XGram donor: fahadalijaved23/XGram, 0c8daa7f2983f830468c73cc94116a1d800d8dd6.
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

import android.content.res.Configuration;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.BaseActivity;
import org.thunderdog.challegram.Log;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.navigation.BackPressMode;
import org.thunderdog.challegram.navigation.HeaderView;
import org.thunderdog.challegram.navigation.NavigationController;
import org.thunderdog.challegram.navigation.NavigationStack;
import org.thunderdog.challegram.navigation.ViewController;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.theme.ColorId;
import org.thunderdog.challegram.theme.ColorState;
import org.thunderdog.challegram.theme.Theme;
import org.thunderdog.challegram.theme.ThemeChangeListener;
import org.thunderdog.challegram.theme.ThemeDelegate;
import org.thunderdog.challegram.theme.ThemeManager;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.tool.Views;
import org.thunderdog.challegram.ui.ChatsController;
import org.thunderdog.challegram.ui.MainController;
import org.thunderdog.challegram.ui.MessagesController;

import moe.kirao.mgx.MoexConfig;

/**
 * Wide windows keep a second chat-list navigation on the leading side. The original
 * navigation owns chats and details on the trailing side, preserving its history
 * when the window becomes narrow. This port deliberately uses moeGramX's own theme.
 */
public final class MoexTwoPane implements NavigationStack.ChangeListener, Lang.Listener {
  private static final float GUTTER_DP = 12f, HANDLE_HEIGHT_DP = 72f, HANDLE_TOUCH_WIDTH_DP = 32f;
  private final BaseActivity context;
  private final NavigationController navigation;
  private final ViewGroup container;
  @Nullable private NavigationController leftNavigation;
  @Nullable private MainController leftMain;
  @Nullable private View divider, placeholder, underlay;
  @Nullable private HandleView handle;
  @Nullable private View hiddenRootView, hiddenHeaderCell;
  @Nullable private MainController headerRoot;
  private boolean headerRootHidden;
  private boolean isActive, destroyed, updatePosted, updating, activityFocused = true;
  private int leftWidth, dragListWidth = -1;
  private int listStart, listEnd, chatStart, chatEnd, gutterStart, gutterEnd;
  // Read by the message loader before the chat's view has been measured.
  private volatile int chatPaneWidth;
  private final MoexPaneResizeGesture expandedResizeGesture = new MoexPaneResizeGesture();
  private int expandedResizeListWidth;
  private boolean expandedResizeStreamOwned;

  public MoexTwoPane (BaseActivity context, NavigationController navigation, ViewGroup container) {
    this.context = context;
    this.navigation = navigation;
    this.container = container;
    navigation.getStack().addChangeListener(this);
    ThemeManager.instance().addThemeListener(themeListener);
    Lang.addLanguageListener(this);
    container.addOnLayoutChangeListener(layoutListener);
    requestUpdate();
  }

  private final View.OnLayoutChangeListener layoutListener = (view, l, t, r, b, oldL, oldT, oldR, oldB) -> {
    if (r - l != oldR - oldL || b - t != oldB - oldT) {
      cancelExpandedResize();
      if (handle != null) handle.cancelDrag();
      requestUpdate();
    }
  };

  private final Runnable updateRunnable = () -> {
    updatePosted = false;
    if (!destroyed) {
      update();
    }
  };

  private void requestUpdate () {
    if (!destroyed && !updatePosted) {
      updatePosted = true;
      container.post(updateRunnable);
    }
  }

  private final ThemeChangeListener themeListener = new ThemeChangeListener() {
    @Override
    public boolean needsTempUpdates () { return true; }

    @Override
    public void onThemeColorsChanged (boolean areTemp, @Nullable ColorState state) {
      recolorPlaceholders();
    }

    @Override
    public void onThemeChanged (ThemeDelegate fromTheme, ThemeDelegate toTheme) {
      MoexTwoPane.this.onThemeChanged();
    }
  };

  private static final class PlaceholderParts {
    final View layout, header;
    final ImageView icon;
    final TextView text;

    PlaceholderParts (View layout, ImageView icon, TextView text, View header) {
      this.layout = layout;
      this.icon = icon;
      this.text = text;
      this.header = header;
    }

    void recolor () {
      layout.setBackgroundColor(Theme.getColor(ColorId.background));
      icon.setColorFilter(Theme.getColor(ColorId.iconLight));
      text.setTextColor(Theme.getColor(ColorId.textLight));
      header.setBackgroundColor(Theme.headerColor());
    }
  }

  private static void recolorPlaceholder (@Nullable View view) {
    if (view != null && view.getTag() instanceof PlaceholderParts) {
      ((PlaceholderParts) view.getTag()).recolor();
    }
  }

  private void recolorPlaceholders () {
    recolorPlaceholder(placeholder);
    recolorPlaceholder(underlay);
    if (divider != null) divider.invalidate();
    if (handle != null) handle.invalidate();
  }

  public boolean isActive () { return isActive; }

  private int usableWindowWidthDp () {
    int width = container.getMeasuredWidth();
    if (width > 0) {
      ViewGroup.LayoutParams params = navigation.getValue().getLayoutParams();
      if (params instanceof ViewGroup.MarginLayoutParams) {
        width -= Math.max(0, ((ViewGroup.MarginLayoutParams) params).leftMargin);
        width -= Math.max(0, ((ViewGroup.MarginLayoutParams) params).rightMargin);
      }
      return Math.round(Math.max(0, width) / Screen.density());
    }
    return context.getResources().getConfiguration().screenWidthDp;
  }

  private int windowHeightDp () {
    // The app window configuration does not shrink to the space above the IME.
    int height = context.getResources().getConfiguration().screenHeightDp;
    return height > 0 ? height : Math.round(container.getMeasuredHeight() / Screen.density());
  }

  public static boolean isWideEnough (BaseActivity context) {
    MoexTwoPane panes = context.moexTwoPane();
    Configuration config = context.getResources().getConfiguration();
    return MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(
      panes != null ? panes.usableWindowWidthDp() : config.screenWidthDp,
      panes != null ? panes.windowHeightDp() : config.screenHeightDp, false);
  }

  @Nullable
  private MainController mainRoot () {
    NavigationStack stack = navigation.getStack();
    ViewController<?> root = stack.size() > 0 ? stack.get(0) : null;
    return root instanceof MainController ? (MainController) root : null;
  }

  public boolean isHiddenRoot (@Nullable ViewController<?> controller) {
    return isActive && controller != null && controller != leftMain && controller == mainRoot();
  }

  private void syncRootHeader () {
    MainController root = mainRoot();
    boolean hidden = isHiddenRoot(root);
    if (root == headerRoot && hidden == headerRootHidden) return;
    if (root != null && navigation.getCurrentStackItem() == root) {
      if (navigation.isAnimating()) return;
      HeaderView header = navigation.getHeaderView();
      if (header != null && !root.inTransformMode()) header.setTitle(root);
    }
    headerRoot = root;
    headerRootHidden = hidden;
  }

  /** Re-evaluate account, setting and current app window after navigation or resizing. */
  public void update () {
    if (destroyed || updating) return;
    updating = true;
    try {
      MainController root = mainRoot();
      boolean allowed = root != null && MoexConfig.twoPaneLayout && !navigation.isDestroyed();
      boolean wide = allowed && MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(usableWindowWidthDp(), windowHeightDp(), isActive);
      try {
        if (wide) {
          if (!isActive || leftMain == null || leftMain.tdlib() != root.tdlib()) {
            activate(root.tdlib());
          } else {
            leftWidth = computeLeftWidth();
            container.requestLayout();
          }
          hideRoot(root);
        } else if (isActive) {
          deactivate(allowed && leftMain != null && leftMain.tdlib() == root.tdlib());
        } else if (leftNavigation != null && (!allowed || leftMain == null || leftMain.tdlib() != root.tdlib())) {
          removeLeft();
        }
      } catch (RuntimeException error) {
        // Keep the existing single-pane navigation usable if the optional layout cannot attach.
        Log.e("moeGramX: two-pane layout failed", error);
        deactivate(false);
      }
      updatePlaceholder();
      updateHighlight();
      syncRootHeader();
      context.notifyBackPressAvailabilityChanged();
    } finally {
      updating = false;
    }
  }

  public boolean isInListPane (float x) {
    return isActive && leftNavigation != null && x >= listStart && x < listEnd;
  }

  public boolean isInChatPane (float x) {
    return !isActive || x >= chatStart && x < chatEnd;
  }

  public boolean isOnRail (float x) { return false; }

  private int computeLeftWidth () {
    int saved = MoexConfig.paneListWidthDp;
    return Screen.dp(saved > 0 ? saved : MoexTwoPaneLayoutPolicy.defaultListWidthDp(usableWindowWidthDp()));
  }

  private void activate (Tdlib tdlib) {
    boolean reuse = leftNavigation != null && leftMain != null && leftMain.tdlib() == tdlib &&
      !leftNavigation.isDestroyed() && !leftMain.isDestroyed();
    if (reuse) detachLeft();
    else if (leftNavigation != null) removeLeft();
    leftWidth = computeLeftWidth();
    if (!reuse) {
      leftNavigation = new NavigationController(context, false);
      leftNavigation.getStack().addChangeListener(stack -> context.notifyBackPressAvailabilityChanged());
      leftMain = new MainController(context, tdlib) {
        @Override
        public void onFocus () {
          // NavigationProcessor posts initial focus. It can arrive after a fast fold, pause or logout.
          if (!isActive || destroyed || !activityFocused) return;
          View focused = focusedChatView();
          super.onFocus();
          restoreChatFocus(focused);
        }
      };
    }
    View leftView = leftNavigation.getValue();
    leftView.setLayoutParams(new FrameLayout.LayoutParams(leftWidth, ViewGroup.LayoutParams.MATCH_PARENT, Gravity.LEFT | Gravity.TOP));
    container.addView(leftView, Math.min(1, container.getChildCount()));
    if (!reuse) leftNavigation.initController(leftMain);
    divider = new DividerView(context);
    divider.setLayoutParams(new FrameLayout.LayoutParams(Screen.dp(GUTTER_DP), ViewGroup.LayoutParams.MATCH_PARENT));
    container.addView(divider, container.indexOfChild(leftView) + 1);
    placeholder = createPlaceholder();
    // The primary header (including its one global player/call bar) stays above the empty-chat page.
    navigation.addViewUnderHeader(placeholder);
    underlay = createPlaceholder();
    container.addView(underlay, container.indexOfChild(navigation.getValue()));
    handle = new HandleView(context);
    handle.setLayoutParams(new FrameLayout.LayoutParams(Screen.dp(GUTTER_DP), Screen.dp(HANDLE_HEIGHT_DP)));
    container.addView(handle, container.indexOfChild(navigation.getValue()) + 1);
    isActive = true;
    if (reuse && activityFocused) focusLeft();
    else if (!activityFocused) leftNavigation.onBlur();
    // Publish the width before chat navigation starts its background message layout.
    computeSplit(container.getMeasuredWidth());
    container.requestLayout();
  }

  private void computeSplit (int width) {
    int insetLeft = 0, insetRight = 0;
    ViewGroup.LayoutParams params = navigation.getValue().getLayoutParams();
    if (params instanceof ViewGroup.MarginLayoutParams) {
      insetLeft = ((ViewGroup.MarginLayoutParams) params).leftMargin;
      insetRight = ((ViewGroup.MarginLayoutParams) params).rightMargin;
    }
    MoexTwoPaneLayoutPolicy.Split split = MoexTwoPaneLayoutPolicy.split(width, insetLeft, insetRight,
      Screen.dp(GUTTER_DP), dragListWidth >= 0 ? dragListWidth : leftWidth, Screen.dp(260f), Screen.dp(300f), Lang.rtl());
    listStart = split.listStart;
    listEnd = split.listEnd;
    chatStart = split.chatStart;
    chatEnd = split.chatEnd;
    gutterStart = split.gutterStart;
    gutterEnd = split.gutterEnd;
    chatPaneWidth = Math.max(0, chatEnd - chatStart);
  }

  /** Called after the activity content's normal measurement, before it lays out its children. */
  public void onMeasure (ViewGroup parent) {
    if (!isActive || leftNavigation == null) {
      chatPaneWidth = 0;
      return;
    }
    computeSplit(parent.getMeasuredWidth());
    int heightSpec = View.MeasureSpec.makeMeasureSpec(parent.getMeasuredHeight(), View.MeasureSpec.EXACTLY);
    int chatSpec = View.MeasureSpec.makeMeasureSpec(chatPaneWidth, View.MeasureSpec.EXACTLY);
    navigation.getValue().measure(chatSpec, heightSpec);
    leftNavigation.getValue().measure(View.MeasureSpec.makeMeasureSpec(listEnd - listStart, View.MeasureSpec.EXACTLY), heightSpec);
    if (placeholder != null) placeholder.measure(chatSpec, heightSpec);
    if (underlay != null) underlay.measure(chatSpec, heightSpec);
    if (divider != null) divider.measure(View.MeasureSpec.makeMeasureSpec(gutterEnd - gutterStart, View.MeasureSpec.EXACTLY), heightSpec);
    if (handle != null) handle.measure(
      View.MeasureSpec.makeMeasureSpec(gutterEnd - gutterStart, View.MeasureSpec.EXACTLY),
      View.MeasureSpec.makeMeasureSpec(Screen.dp(HANDLE_HEIGHT_DP), View.MeasureSpec.EXACTLY));
  }

  public void onLayout (ViewGroup parent) {
    if (!isActive || leftNavigation == null) return;
    int height = parent.getMeasuredHeight();
    navigation.getValue().layout(chatStart, 0, chatEnd, height);
    leftNavigation.getValue().layout(listStart, 0, listEnd, height);
    if (placeholder != null) placeholder.layout(0, 0, chatPaneWidth, height);
    if (underlay != null) underlay.layout(chatStart, 0, chatEnd, height);
    if (divider != null) divider.layout(gutterStart, 0, gutterEnd, height);
    if (handle != null) {
      int h = handle.getMeasuredHeight();
      int header = HeaderView.getSize(true);
      int top = Math.min(Math.max(0, height - h), header + Math.max(0, (height - header - h) / 2));
      handle.layout(gutterStart, top, gutterEnd, top + h);
    }
  }

  /** Observe the handle's small side margins without consuming the underlying click or vertical scroll. */
  public boolean onExpandedResizeTouchEvent (MotionEvent event, boolean gesturesBlocked) {
    int action = event.getActionMasked();
    if (action == MotionEvent.ACTION_DOWN) {
      cancelExpandedResize();
      expandedResizeStreamOwned = false;
    }
    boolean owned = expandedResizeStreamOwned;
    if (!isActive || destroyed || !activityFocused || handle == null || gesturesBlocked ||
        context.isPasscodeShowing() || context.isWindowPopupShowing() ||
        (context.getDrawer() != null && context.getDrawer().isVisible()) ||
        (leftNavigation != null && leftNavigation.isAnimating())) {
      cancelExpandedResize();
      if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) expandedResizeStreamOwned = false;
      return owned;
    }
    if (action == MotionEvent.ACTION_DOWN) {
      float x = event.getX(), y = event.getY();
      float center = (handle.getLeft() + handle.getRight()) / 2f;
      float halfWidth = Screen.dpf(HANDLE_TOUCH_WIDTH_DP) / 2f;
      // The gutter itself still owns its direct click/double-click gesture. Only its side margins are observed.
      boolean inHandle = x >= handle.getLeft() && x < handle.getRight();
      if (!inHandle && x >= center - halfWidth && x < center + halfWidth &&
          y >= handle.getTop() && y < handle.getBottom()) {
        expandedResizeGesture.begin(event.getRawX(), event.getRawY());
        expandedResizeListWidth = listEnd - listStart;
      }
      return false;
    }
    if (event.getPointerCount() != 1 || action == MotionEvent.ACTION_CANCEL) {
      cancelExpandedResize();
      if (action == MotionEvent.ACTION_CANCEL) expandedResizeStreamOwned = false;
      return owned;
    }
    if (action == MotionEvent.ACTION_MOVE) {
      // A lifecycle/multi-touch cancellation keeps swallowing the already-cancelled stream until it ends.
      if (owned && !expandedResizeGesture.isDragging()) return true;
      if (expandedResizeGesture.move(event.getRawX(), event.getRawY(), handle.touchSlop)) {
        if (!owned) {
          expandedResizeStreamOwned = true;
          handle.startTouch(expandedResizeGesture.startX(), expandedResizeGesture.startY(), expandedResizeListWidth);
        }
        handle.moveTouch(event.getRawX(), event.getRawY());
        return true;
      }
    } else if (action == MotionEvent.ACTION_UP) {
      expandedResizeStreamOwned = false;
      expandedResizeGesture.cancel();
      if (owned) handle.finishTouch();
      return owned;
    }
    return false;
  }

  public boolean isExpandedResizeCaptured () {
    return expandedResizeStreamOwned;
  }

  private void cancelExpandedResize () {
    boolean owned = expandedResizeGesture.isDragging();
    expandedResizeGesture.cancel();
    if (owned && handle != null) handle.cancelDrag();
  }

  public static int chatPaneWidth (@Nullable BaseActivity context) {
    MoexTwoPane panes = context != null ? context.moexTwoPane() : null;
    return panes != null ? panes.chatPaneWidth : 0;
  }

  private static volatile long highlightedChatId;
  private static volatile int highlightedAccountId = -1;

  /** Draw path of chat list rows: one comparison when nothing is highlighted. */
  public static boolean isHighlighted (Tdlib tdlib, long chatId) {
    return chatId != 0 && chatId == highlightedChatId && tdlib != null && tdlib.id() == highlightedAccountId;
  }

  private void updateHighlight () {
    long chatId = 0;
    int accountId = -1;
    if (isActive) {
      NavigationStack stack = navigation.getStack();
      for (int i = stack.size() - 1; i >= 1; i--) {
        ViewController<?> c = stack.get(i);
        long id = c != null ? c.getChatId() : 0;
        if (id != 0) {
          chatId = id;
          accountId = c.tdlib() != null ? c.tdlib().id() : -1;
          break;
        }
      }
    }
    if (chatId != highlightedChatId || accountId != highlightedAccountId) {
      highlightedChatId = chatId;
      highlightedAccountId = accountId;
      if (leftNavigation != null) {
        invalidateChatViews(leftNavigation.getValue());
      }
    }
  }

  /** A list row (not a ChatView) that draws the chat open on the right as selected: repainted when that changes. */
  public interface HighlightAware { }

  private static void invalidateChatViews (@Nullable View view) {
    if (view instanceof org.thunderdog.challegram.component.dialogs.ChatView || view instanceof HighlightAware) {
      view.invalidate();
    } else if (view instanceof android.view.ViewGroup) {
      android.view.ViewGroup group = (android.view.ViewGroup) view;
      for (int i = 0; i < group.getChildCount(); i++) {
        invalidateChatViews(group.getChildAt(i));
      }
    }
  }


  public static boolean isPaneChatList (@Nullable ViewController<?> c) {
    if (c == null) {
      return false;
    }
    MoexTwoPane twoPane = c.context().moexTwoPane();
    return twoPane != null && twoPane.leftMain != null && twoPane.leftMain == c;
  }

  /**
   * Space under the last chat of a chat list page in the narrow pane, so the compose button doesn't cover it (also
   * the chat list keeps its compose button at the bottom end of its pane).
   */
  public static int fabSpace (@Nullable ViewController<?> c) {
    if (c == null) {
      return 0;
    }
    return isPaneChatList(c.getParentOrSelf()) ? Screen.dp(56f + 16f + 8f) : 0;
  }


  public @BackPressMode int performOnBackPressed (boolean fromTop, boolean commit) {
    if (isActive && leftNavigation != null) {
      return leftNavigation.performOnBackPressed(fromTop, commit);
    }
    return BackPressMode.SYSTEM_ACTION_REQUIRED;
  }

  public boolean isLeftNavigation (@Nullable NavigationController navigation) {
    return navigation != null && navigation == leftNavigation;
  }

  /** The chat list in the left pane while two panes are shown (keyboard shortcuts act on it), else null. */
  @Nullable
  public MainController leftMain () {
    return isActive ? leftMain : null;
  }

  /**
   * Whether a screen opened from {@code context} should replace what the right pane shows instead of stacking on
   * it: in two panes the chat list stays on the left, so Back never needs to return to an earlier chat or topic
   * list opened from there. True for the left pane's screens and for the right pane's own chat list.
   */
  public static boolean replacesRightPane (@Nullable ViewController<?> context) {
    if (context == null) {
      return false;
    }
    MoexTwoPane twoPane = context.context().moexTwoPane();
    if (twoPane == null || !twoPane.isActive) {
      return false;
    }
    // A chat list inside the main screen's pager has no navigation of its own: its parent (the MainController) does.
    ViewController<?> owner = context.getParentOrSelf();
    NavigationController own = owner.navigationController();
    return twoPane.isLeftNavigation(own) || twoPane.isHiddenRoot(owner);
  }

  /** Right-pane selections, forum topic entry and Back are immediate, as for ordinary chats. */
  public boolean switchesContentImmediately (NavigationController target, ViewController<?> from, ViewController<?> to, boolean forward) {
    return isActive && !destroyed && target == navigation && from != null && to != null &&
      from.tdlib() == to.tdlib() && isPaneContent(from) && isPaneContent(to);
  }

  private boolean isPaneContent (ViewController<?> controller) {
    if (isHiddenRoot(controller) || controller instanceof moe.kirao.mgx.topics.ForumTopicsController) return true;
    if (!(controller instanceof MessagesController)) return false;
    MessagesController messages = (MessagesController) controller;
    return !messages.inPreviewMode() && !messages.isInForceTouchMode() && !messages.areScheduledOnly() &&
      messages.getMessageThread() == null &&
      (messages.getMessageTopicId() == null || messages.getMessageTopicId() instanceof TdApi.MessageTopicForum);
  }

  /** A repeated selection of the visible right chat acts like its existing scroll arrow. */
  public static boolean reselectChatFromList (@Nullable ViewController<?> source, long chatId) {
    if (!(source instanceof ChatsController) || source.isDestroyed() || chatId == 0) return false;
    MoexTwoPane panes = source.context().moexTwoPane();
    if (panes == null || !panes.isActive || panes.destroyed) return false;
    ViewController<?> owner = source.getParentOrSelf();
    NavigationController left = panes.leftNavigation;
    if (left == null || left.isDestroyed() || left.isAnimating() ||
        owner.navigationController() != left || left.getCurrentStackItem() != owner) return false;
    NavigationController right = panes.navigation;
    if (right.isDestroyed() || right.isAnimating()) return false;
    ViewController<?> current = right.getCurrentStackItem();
    if (!(current instanceof MessagesController) || current.isDestroyed() || current.tdlib() != source.tdlib()) return false;
    MessagesController messages = (MessagesController) current;
    if (!messages.canReselectFromChatList() || !messages.compareChat(chatId, null, false)) return false;
    messages.scrollToUnreadOrStartMessage();
    return true;
  }

  /**
   * Puts {@code c} in the chat list pane, over its chat list: anything else above the chat list there (the archive,
   * another list screen) goes first. False when two panes are not shown (or the pane is busy): the caller
   * opens it as usual.
   */
  public static boolean showOnLeft (ViewController<?> context, ViewController<?> c) {
    MoexTwoPane twoPane = context.context().moexTwoPane();
    if (twoPane == null || !twoPane.isActive) {
      return false;
    }
    NavigationController left = twoPane.leftNavigation;
    if (left == null || left.isDestroyed() || left.isAnimating() || left.getStackSize() == 0) {
      return false;
    }
    if (left.getStackSize() > 1) {
      left.setControllerAnimated(c, true, true); // keeps the chat list at the root
    } else {
      left.navigateTo(c);
    }
    return true;
  }

  /** The screen on top of the chat list pane while two panes are shown, else null. */
  @Nullable
  public static ViewController<?> leftTop (@Nullable BaseActivity context) {
    MoexTwoPane twoPane = context != null ? context.moexTwoPane() : null;
    if (twoPane == null || !twoPane.isActive || twoPane.leftNavigation == null || twoPane.leftNavigation.isDestroyed()) {
      return null;
    }
    return twoPane.leftNavigation.getCurrentStackItem();
  }

  /** Whether the chat list pane (two panes shown) has a {@code type} screen on top. */
  public static boolean isOnLeftTop (@Nullable BaseActivity context, Class<?> type) {
    ViewController<?> top = leftTop(context);
    return top != null && type.isInstance(top);
  }

  /** Puts {@code c} on the right pane, replacing anything above the chat list there. */
  public static void showOnRight (ViewController<?> context, ViewController<?> c) {
    NavigationController navigation = context.context().navigation();
    if (navigation == null) {
      return;
    }
    if (navigation.getStackSize() > 1) {
      navigation.setControllerAnimated(c, true, true);
    } else {
      navigation.navigateTo(c);
    }
  }


  private void onDragged (int width) {
    if (dragListWidth != width) {
      dragListWidth = width;
      container.requestLayout();
    }
  }

  private void onDragEnd (boolean commit) {
    if (dragListWidth < 0) return;
    // A fast UP can precede the next measure; clamp the final requested width before saving it.
    if (commit) {
      computeSplit(container.getMeasuredWidth());
      MoexConfig.instance().setPaneListWidthDp(Math.round((listEnd - listStart) / Screen.density()));
    }
    dragListWidth = -1;
    leftWidth = computeLeftWidth();
    container.requestLayout();
  }

  private void resetWidth () {
    dragListWidth = -1;
    MoexConfig.instance().setPaneListWidthDp(0);
    leftWidth = computeLeftWidth();
    container.requestLayout();
  }

  private final class HandleView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF pill = new RectF();
    private final int touchSlop;
    private final MoexPaneResizeGesture resizeGesture = new MoexPaneResizeGesture();
    private int downList;
    private boolean tracking, dragging;
    private long lastTapUp;

    HandleView (android.content.Context context) {
      super(context);
      touchSlop = android.view.ViewConfiguration.get(context).getScaledTouchSlop();
      setContentDescription(Lang.getString(R.string.MoexTwoPaneResize));
      setFocusable(true);
      setClickable(true);
      setOnLongClickListener(view -> {
        resetWidth();
        return true;
      });
    }

    void cancelDrag () {
      resizeGesture.cancel();
      lastTapUp = 0;
      if (tracking) {
        tracking = dragging = false;
        setPressed(false);
        onDragEnd(false);
        invalidate();
      }
    }

    @Override
    public boolean performClick () {
      super.performClick();
      return true;
    }

    @Override
    protected void onDraw (Canvas canvas) {
      float w = Screen.dpf(tracking ? 6f : 4f), h = Screen.dpf(tracking ? 40f : 36f);
      float cx = getWidth() / 2f, cy = getHeight() / 2f;
      pill.set(cx - w / 2f, cy - h / 2f, cx + w / 2f, cy + h / 2f);
      paint.setColor(Theme.getColor(tracking ? ColorId.text : ColorId.iconLight));
      canvas.drawRoundRect(pill, w / 2f, w / 2f, paint);
    }

    void startTouch (float rawX, float rawY, int listWidth) {
      resizeGesture.begin(rawX, rawY);
      downList = listWidth;
      tracking = true;
      dragging = false;
      setPressed(true);
      invalidate();
    }

    void moveTouch (float rawX, float rawY) {
      if (!tracking) return;
      if (resizeGesture.move(rawX, rawY, touchSlop)) {
        if (!dragging) {
          dragging = true;
          lastTapUp = 0;
          performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
        }
        float dx = resizeGesture.deltaX(rawX);
        onDragged(Math.round(Lang.rtl() ? downList - dx : downList + dx));
      } else if (!resizeGesture.isPending()) {
        lastTapUp = 0;
        cancelDrag();
      }
    }

    void finishTouch () {
      if (!tracking) return;
      resizeGesture.cancel();
      tracking = false;
      setPressed(false);
      if (dragging) {
        dragging = false;
        onDragEnd(true);
      } else {
        performClick();
        long now = android.os.SystemClock.uptimeMillis();
        if (lastTapUp != 0 && now - lastTapUp <= android.view.ViewConfiguration.getDoubleTapTimeout()) {
          lastTapUp = 0;
          resetWidth();
        } else lastTapUp = now;
      }
      invalidate();
    }

    @Override
    public boolean onTouchEvent (MotionEvent event) {
      if (event.getPointerCount() != 1) {
        cancelDrag();
        return true;
      }
      switch (event.getActionMasked()) {
        case MotionEvent.ACTION_DOWN:
          if (!isActive) return false;
          if (getParent() != null) getParent().requestDisallowInterceptTouchEvent(true);
          startTouch(event.getRawX(), event.getRawY(), listEnd - listStart);
          return true;
        case MotionEvent.ACTION_MOVE:
          moveTouch(event.getRawX(), event.getRawY());
          return true;
        case MotionEvent.ACTION_UP:
          finishTouch();
          return true;
        case MotionEvent.ACTION_CANCEL:
          cancelDrag();
          return true;
      }
      return tracking;
    }
  }

  /** Keep the same left navigation on fold/resize; discard it on logout, disable or account switch. */
  private void deactivate (boolean keepLeft) {
    if (keepLeft) detachLeft();
    else removeLeft();
    isActive = false;
    chatPaneWidth = 0;
    container.requestLayout();
  }

  private void hideRoot (MainController root) {
    View rootView = root.getValue();
    View headerCell = root.getCustomHeaderCell();
    if (rootView == hiddenRootView && headerCell == hiddenHeaderCell) return;
    showRoot();
    rootView.setClipBounds(new Rect());
    if (headerCell != null) headerCell.setClipBounds(new Rect());
    hiddenRootView = rootView;
    hiddenHeaderCell = headerCell;
  }

  private void showRoot () {
    if (hiddenRootView != null) hiddenRootView.setClipBounds(null);
    if (hiddenHeaderCell != null) hiddenHeaderCell.setClipBounds(null);
    hiddenRootView = hiddenHeaderCell = null;
  }

  private void removeLeft () {
    detachLeft();
    if (leftNavigation != null) {
      leftNavigation.destroy();
      leftNavigation = null;
    }
    leftMain = null;
  }

  private void detachLeft () {
    cancelExpandedResize();
    showRoot();
    if (leftNavigation != null) {
      if (isActive) leftNavigation.onBlur();
      container.removeView(leftNavigation.getValue());
    }
    if (handle != null) {
      handle.cancelDrag();
      container.removeView(handle);
      handle = null;
    }
    if (divider != null) { container.removeView(divider); divider = null; }
    if (placeholder != null) { Views.removeFromParent(placeholder); placeholder = null; }
    if (underlay != null) { container.removeView(underlay); underlay = null; }
  }

  private View createPlaceholder () {
    FrameLayout layout = new FrameLayout(context);
    layout.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    layout.setBackgroundColor(Theme.getColor(ColorId.background));
    layout.setClickable(true);
    LinearLayout content = new LinearLayout(context);
    content.setOrientation(LinearLayout.VERTICAL);
    content.setGravity(Gravity.CENTER_HORIZONTAL);
    content.setPadding(Screen.dp(16f), 0, Screen.dp(16f), 0);
    content.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER));
    ImageView icon = new ImageView(context);
    icon.setImageResource(R.drawable.baseline_forum_96);
    icon.setColorFilter(Theme.getColor(ColorId.iconLight));
    content.addView(icon, new LinearLayout.LayoutParams(Screen.dp(96f), Screen.dp(96f)));
    TextView text = new TextView(context);
    text.setText(Lang.getString(R.string.MoexTwoPaneSelectChat));
    text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 16f);
    text.setTextColor(Theme.getColor(ColorId.textLight));
    text.setGravity(Gravity.CENTER);
    LinearLayout.LayoutParams textParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    textParams.topMargin = Screen.dp(12f);
    content.addView(text, textParams);
    layout.addView(content);
    View header = new View(context);
    header.setBackgroundColor(Theme.headerColor());
    layout.addView(header, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, HeaderView.getSize(true), Gravity.TOP));
    layout.setTag(new PlaceholderParts(layout, icon, text, header));
    return layout;
  }

  private void updatePlaceholder () {
    if (placeholder != null) {
      boolean atRoot = navigation.getStackSize() <= 1 && navigation.getCurrentStackItem() instanceof MainController;
      placeholder.setVisibility(isActive && atRoot ? View.VISIBLE : View.GONE);
    }
  }

  public void onConfigurationChanged (Configuration config) {
    cancelExpandedResize();
    if (leftNavigation != null) leftNavigation.configurationChanged(config);
    if (handle != null) handle.cancelDrag();
    leftWidth = computeLeftWidth();
    update();
    requestUpdate(); // the container may still carry the previous window's measured width
    refreshLabels();
  }

  private void refreshLabels () {
    refreshPlaceholderText(placeholder);
    refreshPlaceholderText(underlay);
    if (handle != null) handle.setContentDescription(Lang.getString(R.string.MoexTwoPaneResize));
  }

  @Override
  public void onLanguagePackEvent (@Lang.EventType int event, int arg1) {
    if (event != Lang.EVENT_PACK_CHANGED && event != Lang.EVENT_DIRECTION_CHANGED && event != Lang.EVENT_STRING_CHANGED) return;
    context.runOnUiThread(() -> {
      if (destroyed) return;
      if (event == Lang.EVENT_PACK_CHANGED || event == Lang.EVENT_STRING_CHANGED) refreshLabels();
      if (Lang.hasDirectionChanged(event, arg1)) {
        cancelExpandedResize();
        if (handle != null) handle.cancelDrag();
        container.requestLayout();
        requestUpdate();
      }
    });
  }

  private static void refreshPlaceholderText (@Nullable View view) {
    if (view != null && view.getTag() instanceof PlaceholderParts) {
      ((PlaceholderParts) view.getTag()).text.setText(Lang.getString(R.string.MoexTwoPaneSelectChat));
    }
  }

  public void onThemeChanged () { recolorPlaceholders(); }

  @Override
  public void onStackChanged (NavigationStack stack) {
    context.runOnUiThread(this::update);
  }

  @Nullable
  private View focusedChatView () {
    View focused = context.getCurrentFocus();
    View current = focused;
    View chat = navigation.getValue();
    while (current != null) {
      if (current == chat) return focused;
      current = current.getParent() instanceof View ? (View) current.getParent() : null;
    }
    return null;
  }

  private static void restoreChatFocus (@Nullable View focused) {
    if (focused != null && focused.isAttachedToWindow()) focused.requestFocus();
  }

  private void focusLeft () {
    View focused = focusedChatView();
    if (leftNavigation != null) leftNavigation.onFocus();
    restoreChatFocus(focused);
  }

  public void onActivityResume () {
    if (!activityFocused) {
      activityFocused = true;
      if (isActive && leftNavigation != null) focusLeft();
    }
  }

  public void onActivityPause () {
    cancelExpandedResize();
    if (handle != null) handle.cancelDrag();
    if (activityFocused) {
      activityFocused = false;
      if (isActive && leftNavigation != null) leftNavigation.onBlur();
    }
  }

  public void onMultiWindowModeChanged (boolean inMultiWindowMode) {
    if (leftNavigation != null) {
      for (ViewController<?> controller : leftNavigation.getStack().getAll()) {
        controller.onMultiWindowModeChanged(inMultiWindowMode);
      }
    }
    requestUpdate();
  }

  public void destroy () {
    if (destroyed) return;
    destroyed = true;
    container.removeCallbacks(updateRunnable);
    container.removeOnLayoutChangeListener(layoutListener);
    navigation.getStack().removeChangeListener(this);
    ThemeManager.instance().removeThemeListener(themeListener);
    Lang.removeLanguageListener(this);
    removeLeft();
    isActive = false;
    chatPaneWidth = 0;
    highlightedChatId = 0;
    highlightedAccountId = -1;
  }

  private static final class DividerView extends View {
    private final Paint paint = new Paint();

    DividerView (android.content.Context context) { super(context); }

    @Override
    protected void onDraw (Canvas canvas) {
      int header = Math.min(getHeight(), HeaderView.getSize(true));
      int line = Math.max(1, Screen.dp(.5f));
      int lineStart = (getWidth() - line) / 2;
      paint.setColor(Theme.headerColor());
      canvas.drawRect(0, 0, getWidth(), header, paint);
      paint.setColor(me.vkryl.core.ColorUtils.fromToArgb(Theme.headerColor(), 0xFF000000, .14f));
      canvas.drawRect(lineStart, 0, lineStart + line, header, paint);
      paint.setColor(Theme.getColor(ColorId.background));
      canvas.drawRect(0, header, getWidth(), getHeight(), paint);
      paint.setColor(Theme.getColor(ColorId.separator));
      canvas.drawRect(lineStart, header, lineStart + line, getHeight(), paint);
    }
  }
}
