package moe.kirao.mgx;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

import tgx.td.ChatId;
import tgx.td.Td;

/**
 * Regex message filtering inspired by AyuGram4A's AyuFilter behavior.
 * This implementation is native to MoeGramX/TDLib and shares no Telegram UI code.
 */
public final class MoexMessageFilter {
  private static volatile List<Pattern> compiledPatterns;

  private MoexMessageFilter () { }

  public static void onConfigChanged () {
    compiledPatterns = null;
  }

  public static boolean matchesRegex (TdApi.Message message) {
    if (!MoexConfig.filterEnabled || message == null) return false;
    TdApi.FormattedText text = Td.textOrCaption(message.content);
    if (text == null || text.text == null || text.text.isEmpty()) return false;
    for (Pattern pattern : patterns()) {
      if (pattern.matcher(text.text).find()) return true;
    }
    return false;
  }

  public static boolean isShadowBanned (Tdlib tdlib, TdApi.Message message) {
    if (tdlib == null || message == null) return false;
    long userId = Td.getSenderUserId(message);
    return isShadowBannedUser(tdlib, userId);
  }

  public static boolean isShadowBannedUser (Tdlib tdlib, long userId) {
    if (tdlib == null || userId == 0) return false;
    return MoexConfig.instance().isShadowBanned(tdlib.id(), userId) ||
      tdlib.chatFullyBlocked(ChatId.fromUserId(userId));
  }

  public static boolean matches (Tdlib tdlib, TdApi.Message message) {
    return isShadowBanned(tdlib, message) || matchesRegex(message);
  }

  public static boolean shouldHideInChat (Tdlib tdlib, TdApi.Message message, boolean isChannel) {
    return isShadowBanned(tdlib, message) || ((MoexConfig.filterInChats || isChannel) && matchesRegex(message));
  }

  private static List<Pattern> patterns () {
    List<Pattern> result = compiledPatterns;
    if (result != null) return result;
    synchronized (MoexMessageFilter.class) {
      result = compiledPatterns;
      if (result != null) return result;
      int flags = Pattern.MULTILINE;
      if (MoexConfig.filterCaseInsensitive) {
        flags |= Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE;
      }
      ArrayList<Pattern> built = new ArrayList<>();
      String raw = MoexConfig.instance().getString(MoexConfig.KEY_FILTER_PATTERNS, "");
      for (String line : raw.split("\\R")) {
        String expression = line.trim();
        if (expression.isEmpty()) continue;
        try {
          built.add(Pattern.compile(expression, flags));
        } catch (PatternSyntaxException ignored) { }
      }
      compiledPatterns = result = Collections.unmodifiableList(built);
      return result;
    }
  }
}
