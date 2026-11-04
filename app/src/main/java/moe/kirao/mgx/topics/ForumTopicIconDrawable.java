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

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.theme.Theme;
import org.thunderdog.challegram.tool.Fonts;

import me.vkryl.core.ColorUtils;
import me.vkryl.core.StringUtils;

/**
 * Default forum topic icon: a speech bubble filled with a vertical gradient in one of the six colors the
 * server allows, with the first letter of the topic name. The General topic uses a "#" instead.
 */
public final class ForumTopicIconDrawable extends Drawable {
  // Server icon_color, gradient bottom, gradient top (official Telegram Android values).
  private static final int[][] COLORS = {
    {0x6FB9F0, 0xFF015EC1, 0xFF4BB7FF},
    {0xFFD67E, 0xFFEA5800, 0xFFFFDB5C},
    {0xCB86DB, 0xFFA438BB, 0xFFE57AFF},
    {0x8EEE98, 0xFF11B411, 0xFF97E334},
    {0xFF93B2, 0xFFE4215A, 0xFFFF7999},
    {0xFB6F5F, 0xFFC61505, 0xFFFF714C}
  };

  /** Server colors a new topic may use, in the official order. */
  public static int[] serverColors () {
    int[] colors = new int[COLORS.length];
    for (int i = 0; i < COLORS.length; i++) {
      colors[i] = COLORS[i][0];
    }
    return colors;
  }

  private static int[] findColors (int iconColor) {
    int r = (iconColor >> 16) & 0xFF, g = (iconColor >> 8) & 0xFF, b = iconColor & 0xFF;
    int[] best = COLORS[0];
    int bestDistance = Integer.MAX_VALUE;
    for (int[] colors : COLORS) {
      int c = colors[0];
      int distance = Math.abs(r - ((c >> 16) & 0xFF)) + Math.abs(g - ((c >> 8) & 0xFF)) + Math.abs(b - (c & 0xFF));
      if (distance < bestDistance) {
        bestDistance = distance;
        best = colors;
      }
    }
    return best;
  }

  private static String firstLetter (@Nullable String name) {
    if (StringUtils.isEmpty(name)) {
      return "";
    }
    String trimmed = name.trim();
    if (trimmed.isEmpty()) {
      return "";
    }
    int end = trimmed.offsetByCodePoints(0, 1);
    return trimmed.substring(0, end).toUpperCase();
  }

  private final boolean isGeneral;
  private final int bottomColor, topColor;
  private final String letter;

  private final Paint fillPaint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.DITHER_FLAG);
  private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.DITHER_FLAG);
  private final Path bubblePath = new Path();
  private boolean isDark;

  public ForumTopicIconDrawable (TdApi.ForumTopicInfo info) {
    this(info.isGeneral, info.icon != null ? info.icon.color : COLORS[0][0], info.name);
  }

  public ForumTopicIconDrawable (boolean isGeneral, int iconColor, @Nullable String name) {
    this.isGeneral = isGeneral;
    int[] colors = findColors(iconColor);
    this.bottomColor = colors[1];
    this.topColor = colors[2];
    this.letter = isGeneral ? "#" : firstLetter(name);
    textPaint.setTypeface(Fonts.getRobotoBold());
    textPaint.setTextAlign(Paint.Align.CENTER);
  }

  @Override
  protected void onBoundsChange (@NonNull Rect bounds) {
    super.onBoundsChange(bounds);
    buildShape(bounds);
  }

  private void buildShape (Rect bounds) {
    float size = Math.min(bounds.width(), bounds.height());
    float left = bounds.left, top = bounds.top;
    bubblePath.reset();
    if (size <= 0) {
      return;
    }
    // Round body with a short tail at the bottom-left corner. Both contours wind the same way,
    // so the default WINDING fill draws their union (Path.op needs API 19).
    float cx = left + size * .5f, cy = top + size * .46f, radius = size * .42f;
    bubblePath.addCircle(cx, cy, radius, Path.Direction.CW);
    bubblePath.moveTo(left + size * .17f, top + size * .66f);
    bubblePath.lineTo(left + size * .42f, top + size * .84f);
    bubblePath.lineTo(left + size * .06f, top + size * .94f);
    bubblePath.close();
    updateShader(bounds);
  }

  private void updateShader (Rect bounds) {
    isDark = Theme.isDark();
    int bottom = isDark ? ColorUtils.fromToArgb(bottomColor, 0xFFFFFFFF, .2f) : bottomColor;
    int top = isDark ? ColorUtils.fromToArgb(topColor, 0xFFFFFFFF, .2f) : topColor;
    fillPaint.setShader(new LinearGradient(0, bounds.bottom, 0, bounds.top, bottom, top, Shader.TileMode.CLAMP));
  }

  @Override
  public void draw (@NonNull Canvas c) {
    Rect bounds = getBounds();
    float size = Math.min(bounds.width(), bounds.height());
    if (size <= 0) {
      return;
    }
    if (isGeneral) {
      textPaint.setColor(Theme.iconColor());
      textPaint.setTextSize(size * .9f);
      drawCenteredText(c, bounds.exactCenterX(), bounds.exactCenterY());
      return;
    }
    if (isDark != Theme.isDark()) {
      updateShader(bounds);
    }
    c.drawPath(bubblePath, fillPaint);
    if (!letter.isEmpty()) {
      textPaint.setColor(0xFFFFFFFF);
      // 13dp letter on a 24dp icon.
      textPaint.setTextSize(size * 13f / 24f);
      drawCenteredText(c, bounds.left + size * .5f, bounds.top + size * .46f);
    }
  }

  private void drawCenteredText (Canvas c, float cx, float cy) {
    Paint.FontMetrics fm = textPaint.getFontMetrics();
    c.drawText(letter, cx, cy - (fm.ascent + fm.descent) / 2f, textPaint);
  }

  @Override
  public void setAlpha (int alpha) {
    fillPaint.setAlpha(alpha);
    textPaint.setAlpha(alpha);
  }

  @Override
  public void setColorFilter (@Nullable ColorFilter colorFilter) {
    fillPaint.setColorFilter(colorFilter);
    textPaint.setColorFilter(colorFilter);
  }

  @Override
  public int getOpacity () {
    return PixelFormat.TRANSLUCENT;
  }
}
