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
package moe.kirao.mgx.topics;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.component.emoji.AnimatedEmojiDrawable;
import org.thunderdog.challegram.component.sticker.TGStickerObj;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.support.RippleSupport;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.theme.ColorId;
import org.thunderdog.challegram.theme.Theme;
import org.thunderdog.challegram.tool.Paints;
import org.thunderdog.challegram.tool.Keyboard;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.tool.UI;
import org.thunderdog.challegram.ui.RecyclerViewController;
import org.thunderdog.challegram.v.CustomRecyclerView;
import org.thunderdog.challegram.widget.MaterialEditTextGroup;

import java.util.ArrayList;
import java.util.List;

/**
 * Create or edit a forum topic: name, color (new topics only, as in the official app) and icon from
 * Telegram's free default topic icon set.
 */
public final class ForumTopicEditController extends RecyclerViewController<ForumTopicEditController.Args> {
  public static final class Args {
    public final TdApi.Chat chat;
    @Nullable public final TdApi.ForumTopic topic;

    /** @param topic null to create a new topic */
    public Args (TdApi.Chat chat, @Nullable TdApi.ForumTopic topic) {
      this.chat = chat;
      this.topic = topic;
    }
  }

  private static final int SPAN_COUNT = 6;
  private static final int VIEW_TYPE_HEADER = 0, VIEW_TYPE_TITLE = 1, VIEW_TYPE_ICON = 2;

  private int color;
  private long customEmojiId;
  private String name = "";
  private final List<TdApi.Sticker> icons = new ArrayList<>();
  private IconView preview;
  private MaterialEditTextGroup nameInput;
  private Adapter adapter;
  private boolean isSaving;

  public ForumTopicEditController (Context context, Tdlib tdlib) {
    super(context, tdlib);
  }

  private boolean isCreating () {
    return getArgumentsStrict().topic == null;
  }

  private boolean isGeneral () {
    TdApi.ForumTopic topic = getArgumentsStrict().topic;
    return topic != null && topic.info.isGeneral;
  }

  @Override
  public int getId () {
    return R.id.controller_xgramTopicEdit;
  }

  @Override
  public CharSequence getName () {
    return Lang.getString(isCreating() ? R.string.XgramNewTopic : R.string.XgramEditTopic);
  }

  @Override
  protected void onCreateView (Context context, CustomRecyclerView recyclerView) {
    TdApi.ForumTopic topic = getArgumentsStrict().topic;
    if (topic != null) {
      name = topic.info.name;
      color = topic.info.icon != null ? topic.info.icon.color : ForumTopicIconDrawable.serverColors()[0];
      customEmojiId = topic.info.icon != null ? topic.info.icon.customEmojiId : 0;
    } else {
      int[] colors = ForumTopicIconDrawable.serverColors();
      color = colors[(int) (Math.random() * colors.length)];
    }

    adapter = new Adapter();
    GridLayoutManager manager = new GridLayoutManager(context, SPAN_COUNT);
    manager.setSpanSizeLookup(new GridLayoutManager.SpanSizeLookup() {
      @Override
      public int getSpanSize (int position) {
        return adapter.getItemViewType(position) == VIEW_TYPE_ICON ? 1 : SPAN_COUNT;
      }
    });
    recyclerView.setLayoutManager(manager);
    recyclerView.setItemAnimator(null);
    recyclerView.setAdapter(adapter);

    if (!isGeneral()) {
      tdlib.send(new TdApi.GetForumTopicDefaultIcons(), (stickers, error) -> runOnUiThreadOptional(() -> {
        if (stickers != null) {
          for (TdApi.Sticker sticker : stickers.stickers) {
            if (sticker.fullType instanceof TdApi.StickerFullTypeCustomEmoji) {
              icons.add(sticker);
            }
          }
          adapter.notifyDataSetChanged();
          if (preview != null) {
            preview.bind(this);
          }
        }
      }));
    }
  }

  @Override
  public void onPrepareToShow () {
    super.onPrepareToShow();
    setDoneVisible(true, false);
  }

  @Override
  public void onFocus () {
    super.onFocus();
    if (isCreating() && nameInput != null) {
      Keyboard.show(nameInput.getEditText());
    }
  }

  private static long emojiIdOf (TdApi.Sticker sticker) {
    return ((TdApi.StickerFullTypeCustomEmoji) sticker.fullType).customEmojiId;
  }

  @Nullable
  private TdApi.Sticker findIcon (long customEmojiId) {
    for (TdApi.Sticker sticker : icons) {
      if (emojiIdOf(sticker) == customEmojiId) {
        return sticker;
      }
    }
    return null;
  }

  private void onIconSelected (long customEmojiId) {
    this.customEmojiId = customEmojiId;
    if (preview != null) {
      preview.bind(this);
    }
    adapter.notifyItemRangeChanged(2, adapter.getItemCount() - 2);
  }

  private void onPreviewClicked () {
    // The server keeps a topic's color forever; only new topics can pick one.
    if (!isCreating() || customEmojiId != 0) {
      return;
    }
    int[] colors = ForumTopicIconDrawable.serverColors();
    int index = 0;
    for (int i = 0; i < colors.length; i++) {
      if (colors[i] == color) {
        index = i;
        break;
      }
    }
    color = colors[(index + 1) % colors.length];
    preview.bind(this);
    adapter.notifyItemRangeChanged(2, 1);
  }

  @Override
  protected void onDoneClick () {
    if (isSaving) {
      return;
    }
    String trimmed = name.trim();
    if (trimmed.isEmpty()) {
      UI.forceVibrateError(getValue());
      return;
    }
    TdApi.Chat chat = getArgumentsStrict().chat;
    TdApi.ForumTopic topic = getArgumentsStrict().topic;
    isSaving = true;
    setDoneProgress(true);
    if (topic == null) {
      tdlib.send(new TdApi.CreateForumTopic(chat.id, trimmed, false, new TdApi.ForumTopicIcon(color, customEmojiId)), (info, error) -> runOnUiThreadOptional(() -> {
        isSaving = false;
        setDoneProgress(false);
        if (error != null) {
          UI.showError(error);
        } else {
          // MessagesController removes this editor from the stack once the topic is shown.
          XgramForums.openTopic(this, chat, info.forumTopicId, 0);
        }
      }));
    } else {
      boolean iconChanged = !isGeneral() && (topic.info.icon == null || topic.info.icon.customEmojiId != customEmojiId);
      tdlib.send(new TdApi.EditForumTopic(chat.id, topic.info.forumTopicId, trimmed, iconChanged, customEmojiId), (ok, error) -> runOnUiThreadOptional(() -> {
        isSaving = false;
        setDoneProgress(false);
        if (error != null) {
          UI.showError(error);
        } else {
          navigateBack();
        }
      }));
    }
  }

  @Override
  public void destroy () {
    super.destroy();
    if (preview != null) {
      preview.performDestroy();
    }
  }

  // Views

  /** Topic icon: the colored letter bubble or a custom emoji. */
  private static final class IconView extends View {
    private final Tdlib tdlib;
    private ForumTopicIconDrawable bubble;
    private AnimatedEmojiDrawable emoji;
    private long emojiId;
    private boolean isSelected, isAttached;

    IconView (Context context, Tdlib tdlib) {
      super(context);
      this.tdlib = tdlib;
    }

    void setBubble (int color, String name) {
      bubble = new ForumTopicIconDrawable(false, color, name);
      invalidate();
    }

    void setEmoji (long emojiId, @Nullable TdApi.Sticker sticker) {
      if (this.emojiId == emojiId) {
        return;
      }
      this.emojiId = emojiId;
      if (emoji != null) {
        emoji.detach();
        emoji.performDestroy();
        emoji = null;
      }
      if (emojiId == 0) {
        invalidate();
        return;
      }
      if (sticker != null) {
        setEmojiSticker(sticker);
        return;
      }
      // Not one of the default icons (Premium users can pick any custom emoji).
      tdlib.emoji().findOrRequest(emojiId, (entry, inPlace) -> {
        Runnable act = () -> {
          if (this.emojiId == emojiId && emoji == null && entry.value != null) {
            setEmojiSticker(entry.value);
          }
        };
        if (inPlace) {
          act.run();
        } else {
          tdlib.ui().post(act);
        }
      });
      invalidate();
    }

    private void setEmojiSticker (TdApi.Sticker sticker) {
      emoji = new AnimatedEmojiDrawable(this);
      emoji.setSticker(new TGStickerObj(tdlib, sticker, null, sticker.fullType), false);
      if (isAttached) {
        emoji.attach();
      }
      invalidate();
    }

    void bind (ForumTopicEditController c) {
      setBubble(c.color, c.name);
      setEmoji(c.customEmojiId, c.customEmojiId != 0 ? c.findIcon(c.customEmojiId) : null);
    }

    void setSelectedIcon (boolean isSelected) {
      if (this.isSelected != isSelected) {
        this.isSelected = isSelected;
        invalidate();
      }
    }

    @Override
    protected void onAttachedToWindow () {
      super.onAttachedToWindow();
      isAttached = true;
      if (emoji != null) {
        emoji.attach();
      }
    }

    @Override
    protected void onDetachedFromWindow () {
      super.onDetachedFromWindow();
      isAttached = false;
      if (emoji != null) {
        emoji.detach();
      }
    }

    void performDestroy () {
      if (emoji != null) {
        emoji.performDestroy();
        emoji = null;
      }
    }

    @Override
    protected void onDraw (Canvas c) {
      int size = Math.min(getMeasuredWidth(), getMeasuredHeight());
      int iconSize = (int) (size * .62f);
      int left = (getMeasuredWidth() - iconSize) / 2, top = (getMeasuredHeight() - iconSize) / 2;
      if (isSelected) {
        Paint paint = Paints.getProgressPaint(Theme.getColor(ColorId.iconActive), Screen.dp(2f));
        c.drawCircle(getMeasuredWidth() / 2f, getMeasuredHeight() / 2f, size / 2f - Screen.dp(4f), paint);
      }
      Drawable d = emoji != null ? emoji : bubble;
      if (d != null) {
        d.setBounds(left, top, left + iconSize, top + iconSize);
        d.draw(c);
      }
    }
  }

  private static final class Holder extends RecyclerView.ViewHolder {
    Holder (View itemView) {
      super(itemView);
    }
  }

  private final class Adapter extends RecyclerView.Adapter<Holder> {
    @Override
    public int getItemCount () {
      // Header, then (unless General) the icon title, "no icon" and the default icons.
      return isGeneral() ? 1 : 3 + icons.size();
    }

    @Override
    public int getItemViewType (int position) {
      return position == 0 ? VIEW_TYPE_HEADER : position == 1 ? VIEW_TYPE_TITLE : VIEW_TYPE_ICON;
    }

    @NonNull
    @Override
    public Holder onCreateViewHolder (@NonNull ViewGroup parent, int viewType) {
      Context context = parent.getContext();
      switch (viewType) {
        case VIEW_TYPE_HEADER: {
          LinearLayout layout = new LinearLayout(context);
          layout.setOrientation(LinearLayout.HORIZONTAL);
          layout.setGravity(Gravity.CENTER_VERTICAL);
          layout.setPadding(Screen.dp(12f), Screen.dp(12f), Screen.dp(16f), Screen.dp(12f));
          layout.setLayoutParams(new RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
          RippleSupport.setSimpleWhiteBackground(layout);

          preview = new IconView(context, tdlib);
          preview.setOnClickListener(v -> onPreviewClicked());
          layout.addView(preview, new LinearLayout.LayoutParams(Screen.dp(64f), Screen.dp(64f)));

          MaterialEditTextGroup input = nameInput = new MaterialEditTextGroup(context, tdlib);
          input.setHint(R.string.XgramTopicNameHint);
          input.setMaxLength(128);
          input.setText(name);
          input.setTextListener((v, text) -> {
            name = text.toString();
            preview.bind(ForumTopicEditController.this);
            adapter.notifyItemRangeChanged(2, 1);
          });
          LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
          params.leftMargin = Screen.dp(8f);
          layout.addView(input, params);
          addThemeInvalidateListener(layout);
          preview.bind(ForumTopicEditController.this);
          return new Holder(layout);
        }
        case VIEW_TYPE_TITLE: {
          TextView title = new TextView(context);
          title.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14f);
          title.setTextColor(Theme.getColor(ColorId.textNeutral));
          addThemeTextColorListener(title, ColorId.textNeutral);
          title.setPadding(Screen.dp(16f), Screen.dp(16f), Screen.dp(16f), Screen.dp(8f));
          title.setText(Lang.getString(isCreating() ? R.string.XgramTopicIconCreateHint : R.string.XgramTopicIcon));
          title.setLayoutParams(new RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
          return new Holder(title);
        }
        case VIEW_TYPE_ICON:
        default: {
          IconView view = new IconView(context, tdlib);
          view.setLayoutParams(new RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Screen.dp(56f)));
          RippleSupport.setTransparentSelector(view);
          view.setOnClickListener(v -> {
            Object tag = v.getTag();
            onIconSelected(tag instanceof Long ? (Long) tag : 0L);
          });
          return new Holder(view);
        }
      }
    }

    @Override
    public void onBindViewHolder (@NonNull Holder holder, int position) {
      if (getItemViewType(position) != VIEW_TYPE_ICON) {
        return;
      }
      IconView view = (IconView) holder.itemView;
      int iconIndex = position - 3;
      if (iconIndex < 0) {
        // "No icon": the colored letter bubble.
        view.setTag(0L);
        view.setBubble(color, name);
        view.setEmoji(0, null);
        view.setSelectedIcon(customEmojiId == 0);
      } else {
        TdApi.Sticker sticker = icons.get(iconIndex);
        long emojiId = emojiIdOf(sticker);
        view.setTag(emojiId);
        view.setEmoji(emojiId, sticker);
        view.setSelectedIcon(customEmojiId == emojiId);
      }
    }
  }
}
