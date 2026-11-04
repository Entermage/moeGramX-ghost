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
 * File created on 16/01/2023
 */
package org.thunderdog.challegram.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Rect;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;

import androidx.annotation.Nullable;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.data.TD;
import org.thunderdog.challegram.navigation.PopupPaneBounds;
import org.thunderdog.challegram.navigation.ViewController;
import org.thunderdog.challegram.support.RippleSupport;
import org.thunderdog.challegram.support.ViewSupport;
import org.thunderdog.challegram.theme.ColorId;
import org.thunderdog.challegram.theme.Theme;
import org.thunderdog.challegram.tool.Drawables;
import org.thunderdog.challegram.tool.Paints;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.tool.Views;
import org.thunderdog.challegram.widget.PopupLayout;
import org.thunderdog.challegram.widget.RootFrameLayout;
import org.thunderdog.challegram.widget.ShadowView;

import java.util.ArrayList;
import java.util.List;

import me.vkryl.android.widget.FrameLayoutFix;
import me.vkryl.core.StringUtils;
import tgx.td.Td;

public class ChatFolderIconSelector {

  private final Context context;
  private final ViewController<?> owner;
  private final Delegate delegate;
  private final IconGridLayout popupView;
  private final GridLayoutManager layoutManager;
  private final @Nullable String selectedIconName;

  private PopupLayout popupLayout;

  public ChatFolderIconSelector (ViewController<?> owner, @Nullable String selectedIconName, boolean isDefault, Delegate delegate) {
    this.context = owner.context();
    this.owner = owner;
    this.delegate = delegate;
    this.selectedIconName = selectedIconName;

    List<ListItem> items = new ArrayList<>(TD.ICON_NAMES.length);
    for (String iconName : TD.ICON_NAMES) {
      items.add(new ListItem(ListItem.TYPE_CUSTOM_SINGLE, 0, TD.iconByName(iconName, 0), 0).setStringValue(iconName));
    }
    SettingsAdapter popupAdapter = new SettingsAdapter(owner, null, owner) {
      @Override
      protected SettingHolder initCustom (ViewGroup parent) {
        ImageView imageView = new ImageView(parent.getContext()) {
          @Override
          protected void onMeasure (int widthMeasureSpec, int heightMeasureSpec) {
            int size = MeasureSpec.getSize(widthMeasureSpec);
            setMeasuredDimension(size, size);
          }

          @Override
          protected void onDraw (Canvas canvas) {
            ListItem item = (ListItem) getTag();
            String iconName = item.getStringValue();
            if (isSelectedIcon(iconName)) {
              canvas.drawCircle(getWidth() / 2f, getHeight() / 2f, Screen.dp(24f), Paints.fillingPaint(Theme.fillingColor()));
            }
            super.onDraw(canvas);
          }
        };
        imageView.setScaleType(ImageView.ScaleType.CENTER);
        Views.setClickable(imageView);
        imageView.setOnClickListener(v -> {
          ListItem item = (ListItem) imageView.getTag();
          String iconName = item.getStringValue();
          TdApi.ChatFolderIcon icon = !StringUtils.isEmpty(iconName) ? new TdApi.ChatFolderIcon(iconName) : null;
          delegate.onIconClick(icon);
          hide(/* animated */ true);
        });
        RippleSupport.setTransparentSelector(imageView);
        return new SettingHolder(imageView);
      }

      @Override
      protected void setCustom (ListItem item, SettingHolder holder, int position) {
        ImageView imageView = (ImageView) holder.itemView;
        int iconResource = item.getIconResource();
        if (iconResource != 0) {
          imageView.setImageDrawable(Drawables.get(imageView.getResources(), iconResource));
          String iconName = item.getStringValue();
          boolean isSelected = !isDefault && isSelectedIcon(iconName);
          int iconColorId = isSelected ? ColorId.iconActive : ColorId.icon;
          imageView.setColorFilter(Theme.getColor(iconColorId));
          owner.removeThemeListenerByTarget(imageView);
          owner.addThemeFilterListener(imageView, iconColorId);
        } else {
          imageView.setImageDrawable(null);
        }
      }
    };

    layoutManager = new GridLayoutManager(context, 3);
    popupAdapter.setItems(items, false);
    RecyclerView recyclerView = new RecyclerView(context);
    recyclerView.setLayoutManager(layoutManager);
    recyclerView.setAdapter(popupAdapter);
    ViewSupport.setThemedBackground(recyclerView, ColorId.background);

    ShadowView shadowView = new ShadowView(context);
    shadowView.setSimpleTopShadow(true);
    owner.addThemeInvalidateListener(shadowView);

    IconGridLayout popupView = new IconGridLayout();
    popupView.addView(shadowView, FrameLayoutFix.newParams(ViewGroup.LayoutParams.MATCH_PARENT, Screen.dp(7f), Gravity.TOP));
    popupView.addView(recyclerView, FrameLayoutFix.newParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP, 0, Screen.dp(7f), 0, 0));
    popupView.setLayoutParams(FrameLayoutFix.newParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM));
    this.popupView = popupView;
  }

  public void show () {
    int popupWidth = popupView.paneBounds.getAvailableWidth(Screen.currentWidth());
    updateGridWidth(popupWidth);
    int spanCount = layoutManager.getSpanCount();
    int rowCount = (layoutManager.getItemCount() + spanCount - 1) / spanCount;
    int popupHeight = rowCount * (popupWidth / spanCount) + Screen.dp(7f);
    popupLayout = new PopupLayout(context);
    popupLayout.init(true);
    popupLayout.setShowListener(popup -> delegate.onShow());
    popupLayout.setDismissListener(popup -> delegate.onDismiss());
    popupLayout.setHideKeyboard();
    popupLayout.setNeedRootInsets();
    // The first estimate already uses the source pane; PopupLayout starts the
    // animation from the measured height after system insets have been applied.
    popupLayout.showSimplePopupView(popupView, popupHeight);
  }

  public void hide (boolean animated) {
    if (popupLayout != null) {
      popupLayout.hideWindow(animated);
      popupLayout = null;
    }
  }

  private final class IconGridLayout extends FrameLayoutFix implements RootFrameLayout.MarginModifier, PopupPaneBounds.Provider {
    private final PopupPaneBounds paneBounds;

    IconGridLayout () {
      super(context);
      paneBounds = new PopupPaneBounds(this, owner);
    }

    @Override
    public PopupPaneBounds getPopupPaneBounds () {
      return paneBounds;
    }

    @Override
    protected void onAttachedToWindow () {
      super.onAttachedToWindow();
      paneBounds.attach();
    }

    @Override
    protected void onDetachedFromWindow () {
      paneBounds.detach();
      super.onDetachedFromWindow();
    }

    @Override
    public void onApplyMarginInsets (View child, LayoutParams params, Rect legacyInsets, Rect insets, Rect insetsWithoutIme) {
      paneBounds.applyInsets(params, insets);
      // Preserve the default FrameLayout's vertical system-inset placement.
      params.topMargin = legacyInsets.top;
      params.bottomMargin = legacyInsets.bottom;
    }

    @Override
    protected void onMeasure (int widthMeasureSpec, int heightMeasureSpec) {
      updateGridWidth(MeasureSpec.getSize(widthMeasureSpec));
      super.onMeasure(widthMeasureSpec, heightMeasureSpec);
    }
  }

  private void updateGridWidth (int width) {
    if (width <= 0) return;
    int spanCount = computeSpanCount(width);
    if (layoutManager.getSpanCount() != spanCount) {
      layoutManager.setSpanCount(spanCount);
    }
  }

  private int computeSpanCount (int width) {
    int itemSize = Screen.dp(56f);
    return Math.max(width / itemSize, 3);
  }

  private boolean isSelectedIcon (@Nullable String iconName) {
    return isSameIcon(selectedIconName, iconName);
  }

  private static boolean isSameIcon (@Nullable String a, @Nullable String b) {
    return StringUtils.equalsOrBothEmpty(a, b) || (isFolderIcon(a) && isFolderIcon(b));
  }

  private static boolean isFolderIcon (@Nullable String iconName) {
    return StringUtils.isEmpty(iconName) || "Custom".equals(iconName);
  }

  public interface Delegate {
    void onIconClick (@Nullable TdApi.ChatFolderIcon icon);

    default void onShow () {}

    default void onDismiss () {}
  }

  public static ChatFolderIconSelector show (ViewController<?> owner, TdApi.ChatFolder chatFolder, Delegate delegate) {
    TdApi.ChatFolderIcon icon = chatFolder.icon;
    boolean isDefault = false;
    if (Td.isEmpty(icon)) {
      icon = owner.tdlib().chatFolderIcon(chatFolder);
      isDefault = true;
    }
    return show(owner, icon, isDefault, delegate);
  }

  public static ChatFolderIconSelector show (ViewController<?> owner, @Nullable TdApi.ChatFolderIcon selectedIcon, boolean isDefault, Delegate delegate) {
    String iconName = selectedIcon != null && !StringUtils.isEmpty(selectedIcon.name) ? selectedIcon.name : null;
    ChatFolderIconSelector selector = new ChatFolderIconSelector(owner, iconName, isDefault || StringUtils.isEmpty(iconName), delegate);
    selector.show();
    return selector;
  }
}
